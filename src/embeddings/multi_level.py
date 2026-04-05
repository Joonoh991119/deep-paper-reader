"""Multi-level structured embedding for paper reading outputs.

Instead of flat chunk embedding, we embed each structured output level
separately, enabling rich semantic queries like:
- "Papers where efficient coding hypothesis was NOT supported"
- "Figures showing set-size effects on precision"
- "Papers with unacknowledged perceptual grouping confounds"
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from src.models import (
    ArgumentStructure,
    DiscussionAnalysis,
    FigureAnalysis,
    PaperReadingResult,
    PaperSkeleton,
)

logger = logging.getLogger(__name__)


@dataclass
class EmbeddingRecord:
    """A single embedding with metadata for storage."""
    text: str
    vector: list[float]
    level: str          # "L0_skeleton", "L1_hypothesis", etc.
    paper_id: str
    metadata: dict[str, Any]


class MultiLevelEmbedder:
    """Embeds structured paper outputs at multiple semantic levels."""

    def __init__(
        self,
        model_name: str = "BAAI/bge-m3",
        dimensions: int = 1024,
        enable_sparse: bool = True,
    ):
        self.model_name = model_name
        self.dimensions = dimensions
        self.enable_sparse = enable_sparse
        self._model = None

    def _load_model(self):
        """Lazy-load the embedding model."""
        if self._model is not None:
            return
        try:
            if "bge-m3" in self.model_name.lower():
                from FlagEmbedding import BGEM3FlagModel
                self._model = BGEM3FlagModel(self.model_name, use_fp16=True)
                self._model_type = "bge-m3"
            else:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self.model_name)
                self._model_type = "sentence-transformer"
            logger.info(f"Loaded embedding model: {self.model_name}")
        except ImportError as e:
            raise RuntimeError(
                f"Embedding model requires additional packages. Error: {e}"
            )

    def _encode(self, texts: list[str]) -> list[list[float]]:
        """Encode texts to dense vectors."""
        self._load_model()
        if self._model_type == "bge-m3":
            result = self._model.encode(texts, return_dense=True, return_sparse=False)
            return result["dense_vecs"].tolist()
        else:
            return self._model.encode(texts).tolist()

    def embed_paper(self, result: PaperReadingResult) -> list[EmbeddingRecord]:
        """Embed all levels of a paper reading result."""
        records: list[EmbeddingRecord] = []
        paper_id = result.skeleton.doi or result.skeleton.title

        # L0: Paper identity
        records.extend(self._embed_skeleton(result.skeleton, paper_id))

        # L1: Hypotheses
        records.extend(self._embed_hypotheses(result.argument, paper_id))

        # L2: Figure analyses
        records.extend(self._embed_figures(result.figures, paper_id))

        # L3: Prediction-match pairs
        records.extend(self._embed_matches(result.figures, paper_id))

        # L4: Discussion analysis
        records.extend(self._embed_discussion(result.discussion, paper_id))

        return records

    # ── Level Embedders ─────────────────────────────────────────

    def _embed_skeleton(self, skeleton: PaperSkeleton, paper_id: str) -> list[EmbeddingRecord]:
        """L0: Paper skeleton — title + abstract + main type."""
        text = (
            f"Title: {skeleton.title}\n"
            f"Abstract: {skeleton.abstract}\n"
            f"Type: {skeleton.paper_type.value}\n"
            f"Keywords: {', '.join(skeleton.keywords)}"
        )
        vectors = self._encode([text])
        return [EmbeddingRecord(
            text=text,
            vector=vectors[0],
            level="L0_skeleton",
            paper_id=paper_id,
            metadata={
                "title": skeleton.title,
                "journal": skeleton.journal,
                "year": skeleton.year,
                "paper_type": skeleton.paper_type.value,
            },
        )]

    def _embed_hypotheses(self, argument: ArgumentStructure, paper_id: str) -> list[EmbeddingRecord]:
        """L1: Each hypothesis as a separate embedding."""
        records = []
        texts = []
        metas = []

        for h in argument.hypotheses:
            text = (
                f"Hypothesis {h.id}: {h.verbal}\n"
                f"Formal: {h.formal}\n"
                f"Metric: {h.key_metric}\n"
                f"Direction: {h.predicted_direction}"
            )
            if h.operationalization:
                text += (
                    f"\nIV: {h.operationalization.independent_variable.name} "
                    f"({', '.join(h.operationalization.independent_variable.levels)})"
                    f"\nDV: {h.operationalization.dependent_variable.name}"
                )
            texts.append(text)
            metas.append({
                "hypothesis_id": h.id,
                "metric": h.key_metric,
                "direction": h.predicted_direction,
                "figures": h.relevant_figures,
            })

        if texts:
            vectors = self._encode(texts)
            for text, vec, meta in zip(texts, vectors, metas):
                records.append(EmbeddingRecord(
                    text=text,
                    vector=vec,
                    level="L1_hypothesis",
                    paper_id=paper_id,
                    metadata=meta,
                ))

        return records

    def _embed_figures(self, figures: FigureAnalysis, paper_id: str) -> list[EmbeddingRecord]:
        """L2: Each figure observation as a separate embedding."""
        records = []
        texts = []
        metas = []

        for obs in figures.observations:
            parts = [f"Figure {obs.figure_id}: {obs.chart_type}"]
            if obs.x_axis:
                parts.append(f"X-axis: {obs.x_axis.label} ({obs.x_axis.unit})")
            if obs.y_axis:
                parts.append(f"Y-axis: {obs.y_axis.label} ({obs.y_axis.unit})")
            for elem in obs.elements:
                parts.append(f"Condition: {elem.label} ({elem.color})")
            parts.extend(obs.main_trends)
            text = "\n".join(parts)
            texts.append(text)
            metas.append({
                "figure_id": obs.figure_id,
                "chart_type": obs.chart_type,
                "x_axis": obs.x_axis.label if obs.x_axis else "",
                "y_axis": obs.y_axis.label if obs.y_axis else "",
            })

        if texts:
            vectors = self._encode(texts)
            for text, vec, meta in zip(texts, vectors, metas):
                records.append(EmbeddingRecord(
                    text=text,
                    vector=vec,
                    level="L2_figure",
                    paper_id=paper_id,
                    metadata=meta,
                ))

        return records

    def _embed_matches(self, figures: FigureAnalysis, paper_id: str) -> list[EmbeddingRecord]:
        """L3: Prediction-observation match pairs."""
        records = []
        texts = []
        metas = []

        for match in figures.matches:
            text = (
                f"Hypothesis {match.hypothesis_id} on Figure {match.figure_id}: "
                f"{match.match_result.value}. "
                f"{match.match_detail}"
            )
            if match.surprises:
                text += f" Surprises: {'; '.join(match.surprises)}"
            if match.concerns:
                text += f" Concerns: {'; '.join(match.concerns)}"
            texts.append(text)
            metas.append({
                "figure_id": match.figure_id,
                "hypothesis_id": match.hypothesis_id,
                "match_result": match.match_result.value,
                "confidence": match.confidence,
            })

        if texts:
            vectors = self._encode(texts)
            for text, vec, meta in zip(texts, vectors, metas):
                records.append(EmbeddingRecord(
                    text=text,
                    vector=vec,
                    level="L3_match",
                    paper_id=paper_id,
                    metadata=meta,
                ))

        return records

    def _embed_discussion(self, discussion: DiscussionAnalysis, paper_id: str) -> list[EmbeddingRecord]:
        """L4: Discussion critical analysis."""
        parts = [
            f"Author interpretation: {discussion.authors_interpretation}",
            f"Evidence strength: {discussion.strength_of_evidence.value}",
            f"Novelty: {discussion.novelty.value}",
            f"Key contribution: {discussion.key_contribution}",
        ]
        for lim in discussion.limitations_unacknowledged:
            parts.append(f"Unacknowledged limitation: {lim.limitation}")
        for alt in discussion.alternatives_not_mentioned:
            parts.append(f"Missed alternative: {alt.explanation}")
        for q in discussion.open_questions:
            parts.append(f"Open question: {q}")

        text = "\n".join(parts)
        vectors = self._encode([text])

        return [EmbeddingRecord(
            text=text,
            vector=vectors[0],
            level="L4_discussion",
            paper_id=paper_id,
            metadata={
                "evidence_strength": discussion.strength_of_evidence.value,
                "novelty": discussion.novelty.value,
                "num_unacknowledged_limitations": len(discussion.limitations_unacknowledged),
                "num_missed_alternatives": len(discussion.alternatives_not_mentioned),
            },
        )]
