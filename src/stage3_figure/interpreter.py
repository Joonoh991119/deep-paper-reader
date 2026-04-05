"""Stage 3: Figure Deep Interpretation with prediction-observation matching.

The key innovation: before interpreting each figure with a VLM,
the system first generates predictions from Stage 2 hypotheses,
then compares predictions against actual observations.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import yaml

from src.llm_backend import LLMBackend
from src.models import (
    ArgumentStructure,
    AxisSpec,
    AxisObservation,
    DataElement,
    DataPoint,
    ErrorBarInfo,
    FigureAnalysis,
    FigureObservation,
    FigurePrediction,
    GroupPrediction,
    MatchResult,
    PaperSkeleton,
    PredictionMatch,
    SignificanceMarker,
)
from src.vlm_backend import VLMBackend

logger = logging.getLogger(__name__)


def _extract_yaml(text: str) -> dict[str, Any]:
    """Extract YAML from LLM/VLM output."""
    text = re.sub(r"```ya?ml\s*", "", text)
    text = re.sub(r"```\s*$", "", text, flags=re.MULTILINE)
    text = text.strip()
    try:
        return yaml.safe_load(text) or {}
    except yaml.YAMLError:
        match = re.search(r"([\w_]+:.*)", text, re.DOTALL)
        if match:
            try:
                return yaml.safe_load(match.group(1)) or {}
            except yaml.YAMLError:
                pass
        return {}


# ─── Structured VLM Prompt ─────────────────────────────────────

FIGURE_INTERPRET_PROMPT = """You are a scientific figure analyst with expertise in neuroscience data visualization.

Given this figure from a neuroscience paper, analyze it precisely and quantitatively.

Caption: {caption}
Context (surrounding paragraph): {context_paragraph}

Analyze:

1. AXES
   - X-axis: label, unit, range, scale (linear/log/categorical)
   - Y-axis: label, unit, range, scale

2. DATA ELEMENTS
   - List each visual element (bars, lines, scatter points)
   - For each: color, line_style (solid/dashed/dotted), marker shape
   - Map each to its legend label / experimental condition

3. ERROR BARS
   - Present? What type? (SEM, SD, 95% CI, or unknown)

4. STATISTICAL ANNOTATIONS
   - Significance markers (*, **, n.s.)? Between which comparisons?

5. QUANTITATIVE READINGS
   - Estimate key values from the plot for each element

6. MAIN TRENDS
   - Dominant patterns, interactions, notable findings

Output ONLY valid YAML (no code fences):
observation:
  chart_type: "..."
  x_axis:
    label: "..."
    unit: "..."
    range: "..."
    scale: "linear"
  y_axis:
    label: "..."
    unit: "..."
    range: "..."
    scale: "linear"
  elements:
    - label: "..."
      color: "..."
      line_style: "..."
      marker: "..."
      estimated_values:
        - x: "..."
          y: 0.0
  error_bars:
    type: "SEM"
    present: true
  significance_markers:
    - comparison: "..."
      marker: "..."
      p_value: "..."
  main_trends:
    - "..."
"""


class FigureInterpreter:
    """Predicts, interprets, and matches figure observations to hypotheses."""

    def __init__(
        self,
        vlm: VLMBackend,
        llm: LLMBackend,
        prediction_specificity: str = "directional",
        num_quantitative_reads: int = 3,
    ):
        self.vlm = vlm
        self.llm = llm
        self.prediction_specificity = prediction_specificity
        self.num_quantitative_reads = num_quantitative_reads

    def analyze(
        self, skeleton: PaperSkeleton, argument: ArgumentStructure
    ) -> FigureAnalysis:
        """Full figure analysis: predict → interpret → match."""
        analysis = FigureAnalysis(paper_id=skeleton.doi)

        # Step 1: Generate predictions from hypotheses
        logger.info("  Generating predictions from hypotheses...")
        for hyp in argument.hypotheses:
            for fig_id in hyp.relevant_figures:
                fig = self._find_figure(skeleton, fig_id)
                if fig is None:
                    continue
                prediction = self._generate_prediction(hyp, fig.caption, fig_id)
                if prediction:
                    analysis.predictions.append(prediction)

        # Step 2: Interpret each figure with VLM
        logger.info("  Interpreting figures with VLM...")
        for fig in skeleton.figures:
            if not fig.image_path or not Path(fig.image_path).exists():
                logger.warning(f"  Skipping {fig.id}: no image file")
                continue

            context = skeleton.section_texts.get("results", "")
            observation = self._interpret_figure(fig.id, fig.image_path, fig.caption, context)
            if observation:
                analysis.observations.append(observation)

        # Step 3: Match predictions to observations
        logger.info("  Matching predictions to observations...")
        for pred in analysis.predictions:
            obs = self._find_observation(analysis, pred.figure_id)
            if obs is None:
                continue
            match = self._match_prediction(pred, obs)
            if match:
                analysis.matches.append(match)

        return analysis

    # ── Prediction Generation ───────────────────────────────────

    def _generate_prediction(
        self, hypothesis, caption: str, figure_id: str
    ) -> FigurePrediction | None:
        """Generate a prediction for what a figure should show given a hypothesis."""
        specificity_instruction = {
            "directional": "Predict direction only (A > B).",
            "quantitative": "Predict approximate magnitudes where possible.",
            "both": "Predict both direction and approximate magnitudes.",
        }.get(self.prediction_specificity, "")

        prompt = (
            f"Hypothesis:\n"
            f"  ID: {hypothesis.id}\n"
            f"  Verbal: {hypothesis.verbal}\n"
            f"  Formal: {hypothesis.formal}\n"
            f"  Key metric: {hypothesis.key_metric}\n"
            f"  Predicted direction: {hypothesis.predicted_direction}\n\n"
            f"Figure: {figure_id}\n"
            f"Caption: {caption}\n\n"
            f"Specificity: {specificity_instruction}\n\n"
            "Based on the hypothesis, predict what this figure should show.\n"
            "Output ONLY valid YAML (no code fences):\n"
            "prediction:\n"
            "  expected_chart_type: \"...\"\n"
            "  expected_x_axis:\n"
            "    label: \"...\"\n"
            "    values: [\"...\"]\n"
            "  expected_y_axis:\n"
            "    label: \"...\"\n"
            "    values: []\n"
            "  expected_groups:\n"
            "    - label: \"...\"\n"
            "      expected_trend: \"...\"\n"
            "  expected_pattern: \"...\"\n"
            "  expected_interaction: \"...\"\n"
            "  expected_statistics: \"...\"\n"
            "  prediction_confidence: 0.7\n"
        )

        system = (
            "You are a neuroscience expert predicting experimental results. "
            "Think carefully: if the hypothesis is true, what MUST the figure show? "
            "Output raw YAML only, no markdown."
        )

        try:
            response = self.llm.complete(system, prompt)
            raw = _extract_yaml(response)
            pred_data = raw.get("prediction", raw)

            groups = []
            for g in pred_data.get("expected_groups", []):
                if isinstance(g, dict):
                    groups.append(GroupPrediction(
                        label=g.get("label", ""),
                        expected_trend=g.get("expected_trend", ""),
                    ))

            x_axis = None
            x_data = pred_data.get("expected_x_axis", {})
            if isinstance(x_data, dict):
                x_axis = AxisSpec(
                    label=x_data.get("label", ""),
                    values=x_data.get("values", []),
                )

            y_axis = None
            y_data = pred_data.get("expected_y_axis", {})
            if isinstance(y_data, dict):
                y_axis = AxisSpec(
                    label=y_data.get("label", ""),
                    values=y_data.get("values", []),
                )

            return FigurePrediction(
                figure_id=figure_id,
                from_hypothesis=hypothesis.id,
                expected_chart_type=pred_data.get("expected_chart_type", ""),
                expected_x_axis=x_axis,
                expected_y_axis=y_axis,
                expected_groups=groups,
                expected_pattern=pred_data.get("expected_pattern", ""),
                expected_interaction=pred_data.get("expected_interaction", ""),
                expected_statistics=pred_data.get("expected_statistics", ""),
                prediction_confidence=float(pred_data.get("prediction_confidence", 0.5)),
            )
        except Exception as e:
            logger.warning(f"Prediction generation failed for {figure_id}: {e}")
            return None

    # ── Figure Interpretation ───────────────────────────────────

    def _interpret_figure(
        self, figure_id: str, image_path: str, caption: str, context: str
    ) -> FigureObservation | None:
        """Interpret a figure using the VLM with structured prompt."""
        try:
            response = self.vlm.interpret_figure(
                image_path=image_path,
                caption=caption,
                context_paragraph=context[:2000],
                structured_prompt=FIGURE_INTERPRET_PROMPT,
            )
            raw = _extract_yaml(response)
            obs_data = raw.get("observation", raw)

            # Parse elements
            elements = []
            for elem in obs_data.get("elements", []):
                if not isinstance(elem, dict):
                    continue
                values = []
                for v in elem.get("estimated_values", []):
                    if isinstance(v, dict):
                        try:
                            values.append(DataPoint(
                                x=str(v.get("x", "")),
                                y=float(v.get("y", 0)),
                            ))
                        except (ValueError, TypeError):
                            pass
                elements.append(DataElement(
                    label=elem.get("label", ""),
                    color=elem.get("color", ""),
                    line_style=elem.get("line_style", ""),
                    marker=elem.get("marker", ""),
                    estimated_values=values,
                ))

            # Parse significance markers
            sig_markers = []
            for sm in obs_data.get("significance_markers", []):
                if isinstance(sm, dict):
                    sig_markers.append(SignificanceMarker(
                        comparison=sm.get("comparison", ""),
                        marker=sm.get("marker", ""),
                        p_value=sm.get("p_value", ""),
                    ))

            # Parse axes
            x_data = obs_data.get("x_axis", {})
            y_data = obs_data.get("y_axis", {})
            x_axis = AxisObservation(**x_data) if isinstance(x_data, dict) else None
            y_axis = AxisObservation(**y_data) if isinstance(y_data, dict) else None

            # Parse error bars
            eb_data = obs_data.get("error_bars", {})
            error_bars = ErrorBarInfo(**eb_data) if isinstance(eb_data, dict) else ErrorBarInfo()

            return FigureObservation(
                figure_id=figure_id,
                chart_type=obs_data.get("chart_type", ""),
                x_axis=x_axis,
                y_axis=y_axis,
                elements=elements,
                error_bars=error_bars,
                significance_markers=sig_markers,
                main_trends=obs_data.get("main_trends", []),
            )
        except Exception as e:
            logger.warning(f"Figure interpretation failed for {figure_id}: {e}")
            return None

    # ── Prediction-Observation Matching ─────────────────────────

    def _match_prediction(
        self, prediction: FigurePrediction, observation: FigureObservation
    ) -> PredictionMatch | None:
        """Compare a prediction to an observation using LLM reasoning."""
        pred_yaml = yaml.dump(prediction.model_dump(mode="json"), default_flow_style=False)
        obs_yaml = yaml.dump(observation.model_dump(mode="json"), default_flow_style=False)

        prompt = (
            f"Prediction (what figure SHOULD show):\n{pred_yaml}\n\n"
            f"Observation (what figure ACTUALLY shows):\n{obs_yaml}\n\n"
            "Compare prediction to observation:\n"
            "1. Does observed pattern match predicted direction?\n"
            "2. Are predicted conditions showing expected relationship?\n"
            "3. Is expected interaction present?\n"
            "4. Any surprises (unpredicted patterns)?\n"
            "5. Any concerns (overlapping error bars, weak effects)?\n\n"
            "Output ONLY valid YAML:\n"
            "match:\n"
            "  match_result: \"supported\"\n"
            "  match_detail: \"...\"\n"
            "  surprises:\n"
            "    - \"...\"\n"
            "  concerns:\n"
            "    - \"...\"\n"
            "  confidence: 0.8\n"
        )

        system = (
            "You are evaluating whether a scientific figure supports a hypothesis. "
            "Be rigorous. 'partially_supported' = correct direction but weak effect. "
            "'ambiguous' = cannot clearly distinguish H from not-H. "
            "Output raw YAML only."
        )

        try:
            response = self.llm.complete(system, prompt)
            raw = _extract_yaml(response)
            match_data = raw.get("match", raw)

            result_str = match_data.get("match_result", "ambiguous")
            try:
                result = MatchResult(result_str)
            except ValueError:
                result = MatchResult.AMBIGUOUS

            return PredictionMatch(
                figure_id=prediction.figure_id,
                hypothesis_id=prediction.from_hypothesis,
                match_result=result,
                match_detail=match_data.get("match_detail", ""),
                surprises=match_data.get("surprises", []),
                concerns=match_data.get("concerns", []),
                confidence=float(match_data.get("confidence", 0.5)),
            )
        except Exception as e:
            logger.warning(f"Prediction matching failed for {prediction.figure_id}: {e}")
            return None

    # ── Helpers ──────────────────────────────────────────────────

    def _find_figure(self, skeleton: PaperSkeleton, fig_id: str):
        """Find a figure by ID in the skeleton."""
        for fig in skeleton.figures:
            if fig.id == fig_id or fig.id.replace("Fig", "Fig ") == fig_id:
                return fig
        return None

    def _find_observation(self, analysis: FigureAnalysis, fig_id: str):
        """Find an observation by figure ID."""
        for obs in analysis.observations:
            if obs.figure_id == fig_id:
                return obs
        return None
