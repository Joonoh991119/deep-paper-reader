"""Stage 4: Critical Discussion Analysis."""

from __future__ import annotations

import logging
import re
from typing import Any

import yaml

from src.llm_backend import LLMBackend
from src.models import (
    AlternativeExplanation,
    ArgumentStructure,
    ConnectionType,
    DiscussionAnalysis,
    EvidenceStrength,
    FieldConnection,
    FigureAnalysis,
    Limitation,
    Novelty,
    PaperSkeleton,
    Severity,
    UnacknowledgedLimitation,
    UnmentionedAlternative,
)

logger = logging.getLogger(__name__)


def _extract_yaml(text: str) -> dict[str, Any]:
    text = re.sub(r"```ya?ml\s*", "", text)
    text = re.sub(r"```\s*$", "", text, flags=re.MULTILINE)
    try:
        return yaml.safe_load(text.strip()) or {}
    except yaml.YAMLError:
        return {}


class DiscussionAnalyzer:
    """Critical analysis of the Discussion section."""

    def __init__(self, llm: LLMBackend, depth: str = "moderate"):
        self.llm = llm
        self.depth = depth

    def analyze(
        self,
        skeleton: PaperSkeleton,
        argument: ArgumentStructure,
        figures: FigureAnalysis,
    ) -> DiscussionAnalysis:
        discussion_text = skeleton.section_texts.get("discussion", "")
        if not discussion_text:
            logger.warning("No discussion section found.")
            return DiscussionAnalysis(paper_id=skeleton.doi)

        # Summarize inputs for prompt
        claim_summary = argument.main_claim.statement if argument.main_claim else "Not extracted"
        hyp_summary = "\n".join(
            f"  {h.id}: {h.verbal} → {h.predicted_direction}"
            for h in argument.hypotheses
        )
        match_summary = "\n".join(
            f"  {m.figure_id} ({m.hypothesis_id}): {m.match_result.value} — {m.match_detail}"
            for m in figures.matches
        )

        depth_instruction = {
            "brief": "Keep analysis concise — focus only on major issues.",
            "moderate": "Provide balanced analysis of strengths and weaknesses.",
            "deep": (
                "Be thorough. Identify every methodological concern, "
                "every alternative explanation the authors missed, "
                "every limitation they failed to acknowledge."
            ),
        }.get(self.depth, "")

        prompt = (
            f"Paper: {skeleton.title}\n"
            f"Main claim: {claim_summary}\n"
            f"Hypotheses:\n{hyp_summary}\n"
            f"Figure results:\n{match_summary}\n\n"
            f"Discussion text:\n{discussion_text[:5000]}\n\n"
            f"Analysis depth: {self.depth}. {depth_instruction}\n\n"
            "Critically analyze the discussion. Output ONLY valid YAML:\n"
            "discussion:\n"
            "  authors_interpretation: \"...\"\n"
            "  interpretation_strength: \"moderate_claim\"\n"
            "  alternatives_mentioned:\n"
            "    - explanation: \"...\"\n"
            "      how_addressed: \"...\"\n"
            "  alternatives_not_mentioned:\n"
            "    - explanation: \"...\"\n"
            "      why_relevant: \"...\"\n"
            "  limitations_acknowledged:\n"
            "    - limitation: \"...\"\n"
            "      severity: \"minor\"\n"
            "  limitations_unacknowledged:\n"
            "    - limitation: \"...\"\n"
            "      severity: \"moderate\"\n"
            "      why_matters: \"...\"\n"
            "  connections:\n"
            "    - type: \"extends\"\n"
            "      target: \"Author Year\"\n"
            "      detail: \"...\"\n"
            "  strength_of_evidence: \"moderate\"\n"
            "  novelty: \"moderate\"\n"
            "  methodological_rigor: \"moderate\"\n"
            "  key_contribution: \"...\"\n"
            "  open_questions:\n"
            "    - \"...\"\n"
        )

        system = (
            "You are an expert neuroscience reviewer. Be constructively critical. "
            "Identify specific methodological concerns, not generic complaints. "
            "For unacknowledged limitations, think about what a rigorous reviewer would flag. "
            "Output raw YAML only, no markdown."
        )

        response = self.llm.complete(system, prompt, max_tokens=4000)
        raw = _extract_yaml(response)
        data = raw.get("discussion", raw)

        return self._parse(skeleton.doi, data)

    def _parse(self, paper_id: str, data: dict) -> DiscussionAnalysis:
        result = DiscussionAnalysis(paper_id=paper_id)
        result.authors_interpretation = data.get("authors_interpretation", "")
        result.interpretation_strength = data.get("interpretation_strength", "moderate_claim")

        for alt in data.get("alternatives_mentioned", []):
            if isinstance(alt, dict):
                result.alternatives_mentioned.append(AlternativeExplanation(
                    explanation=alt.get("explanation", ""),
                    how_addressed=alt.get("how_addressed", ""),
                ))

        for alt in data.get("alternatives_not_mentioned", []):
            if isinstance(alt, dict):
                result.alternatives_not_mentioned.append(UnmentionedAlternative(
                    explanation=alt.get("explanation", ""),
                    why_relevant=alt.get("why_relevant", ""),
                ))

        for lim in data.get("limitations_acknowledged", []):
            if isinstance(lim, dict):
                sev = lim.get("severity", "moderate")
                try:
                    sev = Severity(sev)
                except ValueError:
                    sev = Severity.MODERATE
                result.limitations_acknowledged.append(Limitation(
                    limitation=lim.get("limitation", ""),
                    severity=sev,
                ))

        for lim in data.get("limitations_unacknowledged", []):
            if isinstance(lim, dict):
                sev = lim.get("severity", "moderate")
                try:
                    sev = Severity(sev)
                except ValueError:
                    sev = Severity.MODERATE
                result.limitations_unacknowledged.append(UnacknowledgedLimitation(
                    limitation=lim.get("limitation", ""),
                    severity=sev,
                    why_matters=lim.get("why_matters", ""),
                ))

        for conn in data.get("connections", []):
            if isinstance(conn, dict):
                ct = conn.get("type", "extends")
                try:
                    ct = ConnectionType(ct)
                except ValueError:
                    ct = ConnectionType.EXTENDS
                result.connections.append(FieldConnection(
                    type=ct,
                    target=conn.get("target", ""),
                    detail=conn.get("detail", ""),
                ))

        soe = data.get("strength_of_evidence", "moderate")
        try:
            result.strength_of_evidence = EvidenceStrength(soe)
        except ValueError:
            pass

        nov = data.get("novelty", "moderate")
        try:
            result.novelty = Novelty(nov)
        except ValueError:
            pass

        result.methodological_rigor = data.get("methodological_rigor", "moderate")
        result.key_contribution = data.get("key_contribution", "")
        result.open_questions = data.get("open_questions", [])

        return result
