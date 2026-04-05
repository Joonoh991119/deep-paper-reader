"""Stage 2: Argument Extraction via LLM prompt chain.

Extracts: background claims → gap → main claim → hypotheses → experimental design
"""

from __future__ import annotations

import logging
import re
from typing import Any

import yaml

from src.llm_backend import LLMBackend
from src.models import (
    ArgumentStructure,
    BackgroundClaim,
    ClaimType,
    DVSpec,
    Experiment,
    ExperimentalFactor,
    FactorType,
    GapType,
    Hypothesis,
    MainClaim,
    Operationalization,
    PaperSkeleton,
    ResearchGap,
    VariableSpec,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are an expert scientific paper analyst specializing in neuroscience. "
    "You extract structured information from research papers with precision. "
    "Always output valid YAML. Never include markdown code fences in your output — "
    "output raw YAML only."
)


def _extract_yaml(text: str) -> dict[str, Any]:
    """Extract YAML from LLM output, handling code fences."""
    # Strip markdown code fences if present
    text = re.sub(r"```ya?ml\s*", "", text)
    text = re.sub(r"```\s*$", "", text, flags=re.MULTILINE)
    text = text.strip()
    try:
        return yaml.safe_load(text) or {}
    except yaml.YAMLError as e:
        logger.warning(f"YAML parse error: {e}")
        # Try to extract just the YAML block
        match = re.search(r"([\w_]+:.*)", text, re.DOTALL)
        if match:
            try:
                return yaml.safe_load(match.group(1)) or {}
            except yaml.YAMLError:
                pass
        return {}


class ArgumentExtractor:
    """Extracts the logical argument structure from a paper."""

    def __init__(
        self,
        llm: LLMBackend,
        chain_depth: int = 5,
        formality: str = "semi-formal",
    ):
        self.llm = llm
        self.chain_depth = chain_depth
        self.formality = formality

    def extract(self, skeleton: PaperSkeleton) -> ArgumentStructure:
        """Run the full extraction chain."""
        intro_text = skeleton.section_texts.get("introduction", "")
        methods_text = skeleton.section_texts.get("methods", "")
        results_text = skeleton.section_texts.get("results", "")

        if not intro_text and not skeleton.abstract:
            logger.warning("No introduction text found. Using abstract only.")
            intro_text = skeleton.abstract

        # Build figure inventory string
        fig_inventory = "\n".join(
            f"- {fig.id}: {fig.caption[:100]}..." if len(fig.caption) > 100 else f"- {fig.id}: {fig.caption}"
            for fig in skeleton.figures
        )

        # Step 1: Background claims
        logger.info("  Step 1/5: Extracting background claims...")
        bg_raw = self._extract_background(skeleton.title, skeleton.abstract, intro_text)

        # Step 2: Research gap
        logger.info("  Step 2/5: Identifying research gap...")
        gap_raw = self._extract_gap(bg_raw, intro_text)

        # Step 3: Main claim
        logger.info("  Step 3/5: Extracting main claim...")
        claim_raw = self._extract_claim(gap_raw, skeleton.abstract, intro_text)

        # Step 4: Hypotheses
        logger.info("  Step 4/5: Formalizing hypotheses...")
        hyp_raw = self._extract_hypotheses(
            claim_raw, gap_raw, methods_text, fig_inventory
        )

        # Step 5: Experimental design
        logger.info("  Step 5/5: Mapping experimental design...")
        exp_raw = self._extract_design(methods_text, hyp_raw)

        return self._assemble(skeleton.doi, bg_raw, gap_raw, claim_raw, hyp_raw, exp_raw)

    # ── Prompt Steps ────────────────────────────────────────────

    def _extract_background(self, title: str, abstract: str, intro: str) -> dict:
        prompt = (
            f"Paper title: {title}\n"
            f"Abstract: {abstract}\n\n"
            f"Introduction text:\n{intro[:4000]}\n\n"
            "Extract all background claims. Output YAML:\n"
            "background_claims:\n"
            "  - claim: \"...\"\n"
            "    citations: [\"Author Year\"]\n"
            "    is_consensus: true\n"
            "    domain: \"...\"\n"
        )
        return _extract_yaml(self.llm.complete(SYSTEM_PROMPT, prompt))

    def _extract_gap(self, bg: dict, intro: str) -> dict:
        bg_yaml = yaml.dump(bg, default_flow_style=False)
        prompt = (
            f"Background claims:\n{bg_yaml}\n\n"
            f"Introduction text:\n{intro[:4000]}\n\n"
            "Identify the research gap. Output YAML:\n"
            "research_gap:\n"
            "  statement: \"No study has tested...\"\n"
            "  type: unexplored\n"
            "  prior_attempts:\n"
            "    - \"...\"\n"
        )
        return _extract_yaml(self.llm.complete(SYSTEM_PROMPT, prompt))

    def _extract_claim(self, gap: dict, abstract: str, intro: str) -> dict:
        gap_yaml = yaml.dump(gap, default_flow_style=False)
        prompt = (
            f"Research gap:\n{gap_yaml}\n\n"
            f"Abstract:\n{abstract}\n\n"
            f"Introduction:\n{intro[:3000]}\n\n"
            "Extract the author's main claim. Output YAML:\n"
            "main_claim:\n"
            "  statement: \"We propose/show...\"\n"
            "  claim_type: novel_mechanism\n"
            "  theoretical_framework: \"...\"\n"
        )
        return _extract_yaml(self.llm.complete(SYSTEM_PROMPT, prompt))

    def _extract_hypotheses(
        self, claim: dict, gap: dict, methods: str, fig_inventory: str
    ) -> dict:
        claim_yaml = yaml.dump(claim, default_flow_style=False)
        gap_yaml = yaml.dump(gap, default_flow_style=False)

        formality_instruction = {
            "casual": "State predictions informally.",
            "semi-formal": "Include direction and metric but allow natural language.",
            "formal": (
                "Use strict formal notation: E[DV(cond_A)] > E[DV(cond_B)] when [moderator]. "
                "Every prediction must specify direction, exact metric, and conditions."
            ),
        }.get(self.formality, "")

        prompt = (
            f"Main claim:\n{claim_yaml}\n"
            f"Research gap:\n{gap_yaml}\n"
            f"Methods:\n{methods[:4000]}\n"
            f"Figures available:\n{fig_inventory}\n\n"
            f"Formality level: {self.formality}\n{formality_instruction}\n\n"
            "Formalize each hypothesis. Output YAML:\n"
            "hypotheses:\n"
            "  - id: \"H1\"\n"
            "    verbal: \"If X, then Y...\"\n"
            "    formal: \"E[metric(A)] > E[metric(B)]\"\n"
            "    predicted_direction: \"A > B\"\n"
            "    key_metric: \"...\"\n"
            "    relevant_figures: [\"Fig2a\"]\n"
            "    operationalization:\n"
            "      independent_variable:\n"
            "        name: \"...\"\n"
            "        levels: [\"...\", \"...\"]\n"
            "        type: within\n"
            "      dependent_variable:\n"
            "        name: \"...\"\n"
            "        unit: \"...\"\n"
            "      controls: [\"...\"]\n"
            "    alternative_if_false: \"...\"\n\n"
            "CRITICAL: Each hypothesis MUST have a directional prediction "
            "that can be verified against a specific figure."
        )
        return _extract_yaml(self.llm.complete(SYSTEM_PROMPT, prompt, max_tokens=6000))

    def _extract_design(self, methods: str, hyp: dict) -> dict:
        hyp_yaml = yaml.dump(hyp, default_flow_style=False)
        prompt = (
            f"Methods:\n{methods[:5000]}\n\n"
            f"Hypotheses:\n{hyp_yaml}\n\n"
            "Map the experimental design. Output YAML:\n"
            "experiments:\n"
            "  - id: \"Exp1\"\n"
            "    design: \"2x3 within-subjects\"\n"
            "    factors:\n"
            "      - name: \"...\"\n"
            "        levels: [\"...\"]\n"
            "        type: within\n"
            "    n_participants: 24\n"
            "    measure: \"...\"\n"
            "    statistical_tests: [\"...\"]\n"
            "    maps_to_hypotheses: [\"H1\"]\n"
            "    relevant_figures: [\"Fig2\"]\n"
            "    paradigm: \"...\"\n"
            "    stimuli: \"...\"\n"
            "    procedure_summary: \"...\"\n"
        )
        return _extract_yaml(self.llm.complete(SYSTEM_PROMPT, prompt, max_tokens=4000))

    # ── Assembly ────────────────────────────────────────────────

    def _assemble(
        self,
        paper_id: str,
        bg: dict,
        gap: dict,
        claim: dict,
        hyp: dict,
        exp: dict,
    ) -> ArgumentStructure:
        """Assemble raw YAML dicts into typed ArgumentStructure."""
        structure = ArgumentStructure(paper_id=paper_id)

        # Background claims
        for bc in bg.get("background_claims", []):
            if isinstance(bc, dict):
                structure.background_claims.append(BackgroundClaim(
                    claim=bc.get("claim", ""),
                    citations=bc.get("citations", []),
                    is_consensus=bc.get("is_consensus", True),
                    domain=bc.get("domain", ""),
                ))

        # Research gap
        gap_data = gap.get("research_gap", gap)
        if isinstance(gap_data, dict) and "statement" in gap_data:
            structure.research_gap = ResearchGap(
                statement=gap_data["statement"],
                type=GapType(gap_data.get("type", "unexplored")),
                prior_attempts=gap_data.get("prior_attempts", []),
            )

        # Main claim
        claim_data = claim.get("main_claim", claim)
        if isinstance(claim_data, dict) and "statement" in claim_data:
            ct = claim_data.get("claim_type", "novel_mechanism")
            try:
                ct = ClaimType(ct)
            except ValueError:
                ct = ClaimType.NOVEL_MECHANISM
            structure.main_claim = MainClaim(
                statement=claim_data["statement"],
                claim_type=ct,
                theoretical_framework=claim_data.get("theoretical_framework", ""),
            )

        # Hypotheses
        for h in hyp.get("hypotheses", []):
            if not isinstance(h, dict):
                continue
            op_data = h.get("operationalization", {})
            op = None
            if isinstance(op_data, dict) and "independent_variable" in op_data:
                iv = op_data["independent_variable"]
                dv = op_data.get("dependent_variable", {})
                ft = iv.get("type", "within")
                try:
                    ft = FactorType(ft)
                except ValueError:
                    ft = FactorType.WITHIN
                op = Operationalization(
                    independent_variable=VariableSpec(
                        name=iv.get("name", ""),
                        levels=iv.get("levels", []),
                        type=ft,
                    ),
                    dependent_variable=DVSpec(
                        name=dv.get("name", ""),
                        unit=dv.get("unit", ""),
                        measurement=dv.get("measurement", ""),
                    ),
                    controls=op_data.get("controls", []),
                )

            structure.hypotheses.append(Hypothesis(
                id=h.get("id", ""),
                verbal=h.get("verbal", ""),
                formal=h.get("formal", ""),
                predicted_direction=h.get("predicted_direction", ""),
                is_directional=bool(h.get("predicted_direction")),
                relevant_figures=h.get("relevant_figures", []),
                key_metric=h.get("key_metric", ""),
                operationalization=op,
                alternative_if_false=h.get("alternative_if_false", ""),
            ))

        # Experiments
        for e in exp.get("experiments", []):
            if not isinstance(e, dict):
                continue
            factors = []
            for f in e.get("factors", []):
                if isinstance(f, dict):
                    ft = f.get("type", "within")
                    try:
                        ft = FactorType(ft)
                    except ValueError:
                        ft = FactorType.WITHIN
                    factors.append(ExperimentalFactor(
                        name=f.get("name", ""),
                        levels=f.get("levels", []),
                        type=ft,
                    ))
            structure.experiments.append(Experiment(
                id=e.get("id", ""),
                design=e.get("design", ""),
                factors=factors,
                n_participants=e.get("n_participants", 0),
                measure=e.get("measure", ""),
                statistical_tests=e.get("statistical_tests", []),
                maps_to_hypotheses=e.get("maps_to_hypotheses", []),
                relevant_figures=e.get("relevant_figures", []),
                paradigm=e.get("paradigm", ""),
                stimuli=e.get("stimuli", ""),
                procedure_summary=e.get("procedure_summary", ""),
            ))

        return structure
