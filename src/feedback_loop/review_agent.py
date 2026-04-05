"""Review Agent: Automated quality critic for pipeline outputs.

Scores each stage's output on multiple dimensions using an LLM.
Results feed into the feedback loop for parameter adjustment.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import yaml

from src.llm_backend import LLMBackend
from src.models import (
    ArgumentStructure,
    DiscussionAnalysis,
    FigureAnalysis,
    PaperSkeleton,
    ParameterAdjustment,
    ReviewScore,
    StageReview,
)

logger = logging.getLogger(__name__)


def _extract_yaml(text: str) -> dict[str, Any]:
    text = re.sub(r"```ya?ml\s*", "", text)
    text = re.sub(r"```\s*$", "", text, flags=re.MULTILINE)
    try:
        return yaml.safe_load(text.strip()) or {}
    except yaml.YAMLError:
        return {}


REVIEW_SYSTEM = (
    "You are a quality review agent for an automated scientific paper reading pipeline. "
    "Score each dimension 1-5:\n"
    "  5: Expert-level, no corrections needed\n"
    "  4: Good, minor improvements possible\n"
    "  3: Adequate but needs improvement\n"
    "  2: Significant errors\n"
    "  1: Wrong or misleading\n"
    "Be harsh but fair. Output raw YAML only, no markdown fences."
)


class ReviewAgent:
    """LLM-based quality critic for pipeline outputs."""

    def __init__(self, llm: LLMBackend):
        self.llm = llm

    def review_all(
        self,
        skeleton: PaperSkeleton,
        argument: ArgumentStructure,
        figures: FigureAnalysis,
        discussion: DiscussionAnalysis,
    ) -> StageReview:
        """Review all stages and produce an aggregate score."""
        all_scores: list[ReviewScore] = []
        all_issues: list[str] = []
        all_adjustments: list[ParameterAdjustment] = []

        # Review each stage
        for stage_name, stage_data, rubric in [
            ("stage1", skeleton, self._skeleton_rubric(skeleton)),
            ("stage2", argument, self._argument_rubric(skeleton, argument)),
            ("stage3", figures, self._figure_rubric(skeleton, argument, figures)),
            ("stage4", discussion, self._discussion_rubric(skeleton, argument, discussion)),
        ]:
            try:
                review = self._review_stage(stage_name, rubric)
                all_scores.extend(review.scores)
                all_issues.extend(review.critical_issues)
                all_adjustments.extend(review.suggested_parameter_changes)
            except Exception as e:
                logger.warning(f"Review failed for {stage_name}: {e}")

        overall = (
            sum(s.score for s in all_scores) / len(all_scores)
            if all_scores
            else 0.0
        )

        return StageReview(
            stage="all",
            paper_id=skeleton.doi,
            scores=all_scores,
            overall_score=round(overall, 2),
            critical_issues=all_issues,
            suggested_parameter_changes=all_adjustments,
        )

    def _review_stage(self, stage_name: str, prompt: str) -> StageReview:
        """Review a single stage."""
        response = self.llm.complete(REVIEW_SYSTEM, prompt, temperature=0.3)
        raw = _extract_yaml(response)
        review_data = raw.get("review", raw)

        scores = []
        for s in review_data.get("scores", []):
            if isinstance(s, dict):
                scores.append(ReviewScore(
                    dimension=f"{stage_name}.{s.get('dimension', 'unknown')}",
                    score=int(s.get("score", 3)),
                    justification=s.get("justification", ""),
                    correction=s.get("correction", ""),
                ))

        adjustments = []
        for a in review_data.get("suggested_parameter_changes", []):
            if isinstance(a, dict):
                adjustments.append(ParameterAdjustment(
                    parameter=a.get("parameter", ""),
                    old_value=str(a.get("current", "")),
                    new_value=str(a.get("suggested", "")),
                ))

        overall = review_data.get("overall_score", 3.0)

        return StageReview(
            stage=stage_name,
            paper_id="",
            scores=scores,
            overall_score=float(overall),
            critical_issues=review_data.get("critical_issues", []),
            suggested_parameter_changes=adjustments,
        )

    # ── Rubric Generators ───────────────────────────────────────

    def _skeleton_rubric(self, skeleton: PaperSkeleton) -> str:
        skeleton_summary = (
            f"Title: {skeleton.title}\n"
            f"Sections found: {len(skeleton.sections)}\n"
            f"Figures: {len(skeleton.figures)}\n"
            f"Tables: {len(skeleton.tables)}\n"
            f"Equations: {len(skeleton.equations)}\n"
        )
        return (
            f"Stage: stage1 (Skeleton Scan)\n\n"
            f"Pipeline output:\n{skeleton_summary}\n"
            f"Section types: {[s.type.value for s in skeleton.sections]}\n\n"
            "Score these dimensions:\n"
            "- section_boundaries: Were all sections correctly identified and typed?\n"
            "- figure_caption_pairing: Are figures paired with correct captions?\n"
            "- reading_order: Is text in correct reading order?\n"
            "- equation_completeness: Are equations complete and well-formatted?\n\n"
            "Output YAML with scores for each dimension."
        )

    def _argument_rubric(self, skeleton: PaperSkeleton, argument: ArgumentStructure) -> str:
        arg_yaml = yaml.dump(argument.model_dump(mode="json"), default_flow_style=False)
        return (
            f"Stage: stage2 (Argument Extraction)\n\n"
            f"Paper abstract:\n{skeleton.abstract[:1000]}\n\n"
            f"Pipeline output:\n{arg_yaml[:3000]}\n\n"
            "Score these dimensions:\n"
            "- gap_identification: Is the research gap specific and correct?\n"
            "- hypothesis_formality: Are hypotheses testable with direction, metric, conditions?\n"
            "- operationalization: Are IV/DV/controls correctly mapped?\n"
            "- design_mapping: Is the factorial structure correct?\n\n"
            "Output YAML with scores."
        )

    def _figure_rubric(
        self, skeleton: PaperSkeleton, argument: ArgumentStructure, figures: FigureAnalysis
    ) -> str:
        fig_yaml = yaml.dump(figures.model_dump(mode="json"), default_flow_style=False)
        return (
            f"Stage: stage3 (Figure Interpretation)\n\n"
            f"Number of predictions: {len(figures.predictions)}\n"
            f"Number of observations: {len(figures.observations)}\n"
            f"Number of matches: {len(figures.matches)}\n\n"
            f"Pipeline output (first 3000 chars):\n{fig_yaml[:3000]}\n\n"
            "Score these dimensions:\n"
            "- axes_identification: Are axes correctly identified (label, unit, range)?\n"
            "- legend_mapping: Are conditions correctly linked to visual elements?\n"
            "- quantitative_reading: Are estimated values reasonable?\n"
            "- error_bar_type: Are error bars correctly identified?\n"
            "- prediction_match: Are match judgments logically sound?\n\n"
            "Output YAML with scores."
        )

    def _discussion_rubric(
        self, skeleton: PaperSkeleton, argument: ArgumentStructure, discussion: DiscussionAnalysis
    ) -> str:
        disc_yaml = yaml.dump(discussion.model_dump(mode="json"), default_flow_style=False)
        return (
            f"Stage: stage4 (Discussion Analysis)\n\n"
            f"Pipeline output:\n{disc_yaml[:3000]}\n\n"
            "Score these dimensions:\n"
            "- author_interpretation: Is the author's conclusion accurately captured?\n"
            "- alternative_explanations: Are missed alternatives genuinely relevant?\n"
            "- limitations: Are unacknowledged limitations real methodological issues?\n\n"
            "Output YAML with scores."
        )
