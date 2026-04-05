"""Pipeline orchestrator — chains all stages and manages the feedback loop.

Usage:
    from src.pipeline import DeepPaperReader
    
    reader = DeepPaperReader()
    result = reader.process("paper.pdf")
    result.skeleton.title  # "Efficient coding in visual working memory"
    result.argument.hypotheses[0].formal  # "E[precision(A)] > E[precision(B)]"
    result.figures.matches[0].match_result  # "supported"
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

from src.config import ModelRegistry, PipelineConfig
from src.llm_backend import create_llm_backend
from src.models import (
    ArgumentStructure,
    DiscussionAnalysis,
    FigureAnalysis,
    PaperReadingResult,
    PaperSkeleton,
    StageReview,
)
from src.vlm_backend import create_vlm_backend

logger = logging.getLogger(__name__)


class DeepPaperReader:
    """Main pipeline: PDF → structured deep reading with feedback."""

    def __init__(
        self,
        config_path: str | Path | None = None,
        registry_path: str | Path | None = None,
    ):
        self.config = PipelineConfig(config_path)
        self.registry = ModelRegistry(registry_path)

        # Lazy-initialized backends
        self._skeleton_vlm = None
        self._figure_vlm = None
        self._reasoning_llm = None

    # ── Backend Accessors ───────────────────────────────────────

    @property
    def skeleton_vlm(self):
        if self._skeleton_vlm is None:
            self._skeleton_vlm = create_vlm_backend(self.config.skeleton_vlm)
        return self._skeleton_vlm

    @property
    def figure_vlm(self):
        if self._figure_vlm is None:
            self._figure_vlm = create_vlm_backend(self.config.figure_vlm)
        return self._figure_vlm

    @property
    def reasoning_llm(self):
        if self._reasoning_llm is None:
            self._reasoning_llm = create_llm_backend(self.config.reasoning_model)
        return self._reasoning_llm

    # ── Full Pipeline ───────────────────────────────────────────

    def process(
        self,
        pdf_path: str | Path,
        enable_review: bool | None = None,
        stages: list[str] | None = None,
    ) -> PaperReadingResult:
        """Process a paper through all (or selected) stages.

        Args:
            pdf_path: Path to the PDF file.
            enable_review: Override config's review_agent setting.
            stages: List of stages to run. Default: all four.
                    Options: ["skeleton", "argument", "figure", "discussion"]

        Returns:
            PaperReadingResult with all structured outputs.
        """
        start_time = time.time()
        stages = stages or ["skeleton", "argument", "figure", "discussion"]
        if enable_review is None:
            enable_review = self.config.review_agent_enabled

        logger.info(f"Processing: {pdf_path}")
        logger.info(f"Stages: {stages}")

        # Stage 1: Skeleton
        skeleton = PaperSkeleton()
        if "skeleton" in stages:
            logger.info("── Stage 1: Skeleton Scan ──")
            skeleton = self._run_stage1(pdf_path)
            logger.info(
                f"   Extracted: {len(skeleton.figures)} figures, "
                f"{len(skeleton.tables)} tables, "
                f"{len(skeleton.equations)} equations"
            )

        # Stage 2: Argument
        argument = ArgumentStructure(paper_id=skeleton.doi)
        if "argument" in stages:
            logger.info("── Stage 2: Argument Extraction ──")
            argument = self._run_stage2(skeleton)
            logger.info(
                f"   Found: {len(argument.hypotheses)} hypotheses, "
                f"{len(argument.experiments)} experiments"
            )

        # Stage 3: Figure
        figures = FigureAnalysis(paper_id=skeleton.doi)
        if "figure" in stages:
            logger.info("── Stage 3: Figure Deep Interpretation ──")
            figures = self._run_stage3(skeleton, argument)
            logger.info(
                f"   Analyzed: {len(figures.observations)} figures, "
                f"{len(figures.matches)} prediction matches"
            )

        # Stage 4: Discussion
        discussion = DiscussionAnalysis(paper_id=skeleton.doi)
        if "discussion" in stages:
            logger.info("── Stage 4: Discussion Analysis ──")
            discussion = self._run_stage4(skeleton, argument, figures)

        # Review Agent
        review = None
        if enable_review:
            logger.info("── Review Agent ──")
            review = self._run_review(skeleton, argument, figures, discussion)
            logger.info(f"   Overall score: {review.overall_score:.1f}/5")

        elapsed = time.time() - start_time
        logger.info(f"── Done in {elapsed:.1f}s ──")

        return PaperReadingResult(
            skeleton=skeleton,
            argument=argument,
            figures=figures,
            discussion=discussion,
            review=review,
            processing_time_seconds=elapsed,
        )

    # ── Stage Implementations ───────────────────────────────────

    def _run_stage1(self, pdf_path: str | Path) -> PaperSkeleton:
        """Stage 1: Parse PDF → PaperSkeleton with VLM figure descriptions."""
        from src.stage1_skeleton.parser import SkeletonBuilder

        builder = SkeletonBuilder(
            parser=self.config.parser,
            language="en",
        )
        skeleton = builder.build(pdf_path)

        # Add VLM descriptions for each figure
        for fig in skeleton.figures:
            if fig.image_path and Path(fig.image_path).exists():
                try:
                    fig.vlm_initial_description = self.skeleton_vlm.describe_figure(
                        fig.image_path, fig.caption
                    )
                except Exception as e:
                    logger.warning(f"VLM description failed for {fig.id}: {e}")
                    fig.vlm_initial_description = f"[VLM error: {e}]"

        return skeleton

    def _run_stage2(self, skeleton: PaperSkeleton) -> ArgumentStructure:
        """Stage 2: Extract argument structure via prompt chain."""
        from src.stage2_argument.extractor import ArgumentExtractor

        extractor = ArgumentExtractor(
            llm=self.reasoning_llm,
            chain_depth=self.config.prompt_chain_depth,
            formality=self.config.hypothesis_formality,
        )
        return extractor.extract(skeleton)

    def _run_stage3(
        self, skeleton: PaperSkeleton, argument: ArgumentStructure
    ) -> FigureAnalysis:
        """Stage 3: Predict → Interpret → Match for each figure."""
        from src.stage3_figure.interpreter import FigureInterpreter

        interpreter = FigureInterpreter(
            vlm=self.figure_vlm,
            llm=self.reasoning_llm,
            prediction_specificity=self.config.prediction_specificity,
            num_quantitative_reads=self.config.num_quantitative_reads,
        )
        return interpreter.analyze(skeleton, argument)

    def _run_stage4(
        self,
        skeleton: PaperSkeleton,
        argument: ArgumentStructure,
        figures: FigureAnalysis,
    ) -> DiscussionAnalysis:
        """Stage 4: Critical discussion analysis."""
        from src.stage4_discussion.analyzer import DiscussionAnalyzer

        analyzer = DiscussionAnalyzer(
            llm=self.reasoning_llm,
            depth=self.config.critical_depth,
        )
        return analyzer.analyze(skeleton, argument, figures)

    def _run_review(
        self,
        skeleton: PaperSkeleton,
        argument: ArgumentStructure,
        figures: FigureAnalysis,
        discussion: DiscussionAnalysis,
    ) -> StageReview:
        """Run the Review Agent on all outputs."""
        from src.feedback_loop.review_agent import ReviewAgent

        agent = ReviewAgent(llm=self.reasoning_llm)
        return agent.review_all(skeleton, argument, figures, discussion)


# ─── CLI Entry Point ────────────────────────────────────────────

def main():
    """CLI entry point for the Deep Paper Reader."""
    import argparse
    import json
    import sys

    import yaml

    parser = argparse.ArgumentParser(
        description="Deep Paper Reader — Comprehension-driven scientific paper analysis"
    )
    parser.add_argument("pdf", help="Path to PDF file")
    parser.add_argument("-o", "--output-dir", default="./output", help="Output directory")
    parser.add_argument("-c", "--config", default=None, help="Config file path")
    parser.add_argument("--no-review", action="store_true", help="Disable review agent")
    parser.add_argument(
        "--stages",
        nargs="+",
        default=None,
        choices=["skeleton", "argument", "figure", "discussion"],
        help="Run only specific stages",
    )
    parser.add_argument(
        "--format",
        choices=["yaml", "json"],
        default="yaml",
        help="Output format",
    )
    parser.add_argument("-v", "--verbose", action="store_true")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    reader = DeepPaperReader(config_path=args.config)
    result = reader.process(
        args.pdf,
        enable_review=not args.no_review,
        stages=args.stages,
    )

    # Save output
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    data = result.model_dump(mode="json")

    if args.format == "yaml":
        out_file = out_dir / "reading_result.yaml"
        with open(out_file, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
    else:
        out_file = out_dir / "reading_result.json"
        with open(out_file, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"\n✓ Output saved to: {out_file}")
    print(f"  Processing time: {result.processing_time_seconds:.1f}s")
    if result.review:
        print(f"  Review score: {result.review.overall_score:.1f}/5")


if __name__ == "__main__":
    main()
