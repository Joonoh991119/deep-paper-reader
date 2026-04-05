"""Stage 1: Skeleton Scan — PDF to structured paper skeleton.

Wraps MinerU (or alternative parser) to extract:
- Section structure
- Figures with captions
- Tables
- Equations
- Quick VLM descriptions of each figure
"""

from __future__ import annotations

import json
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from src.models import (
    Author,
    EquationInfo,
    FigureInfo,
    PaperSkeleton,
    PaperType,
    SectionInfo,
    SectionType,
    TableInfo,
)

logger = logging.getLogger(__name__)


# ─── Section Type Classifier ───────────────────────────────────

_SECTION_KEYWORDS: dict[SectionType, list[str]] = {
    SectionType.INTRODUCTION: ["introduction", "background", "intro"],
    SectionType.METHODS: [
        "method", "methods", "materials", "procedure", "participants",
        "experimental design", "stimuli", "apparatus", "fmri",
    ],
    SectionType.RESULTS: ["result", "results", "findings"],
    SectionType.DISCUSSION: [
        "discussion", "general discussion", "conclusion", "concluding",
        "limitations", "future directions",
    ],
    SectionType.SUPPLEMENTARY: ["supplementary", "supplemental", "appendix", "supporting"],
    SectionType.REFERENCES: ["reference", "references", "bibliography"],
}


def classify_section(title: str) -> SectionType:
    """Classify a section heading into a SectionType."""
    lower = title.lower().strip()
    for stype, keywords in _SECTION_KEYWORDS.items():
        for kw in keywords:
            if kw in lower:
                return stype
    return SectionType.OTHER


# ─── MinerU Parser Wrapper ─────────────────────────────────────

class MinerUParser:
    """Wraps MinerU (magic-pdf) for PDF parsing."""

    def __init__(self, language: str = "en", output_format: str = "json"):
        self.language = language
        self.output_format = output_format

    def parse(self, pdf_path: str | Path) -> dict[str, Any]:
        """Parse a PDF using MinerU and return structured JSON output."""
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        with tempfile.TemporaryDirectory() as tmpdir:
            cmd = [
                "magic-pdf",
                "-p", str(pdf_path),
                "-o", tmpdir,
                "-m", "auto",
                "--lang", self.language,
            ]
            logger.info(f"Running MinerU: {' '.join(cmd)}")

            try:
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=300
                )
                if result.returncode != 0:
                    logger.error(f"MinerU failed: {result.stderr}")
                    raise RuntimeError(f"MinerU parsing failed: {result.stderr[:500]}")
            except FileNotFoundError:
                raise RuntimeError(
                    "MinerU (magic-pdf) not found. Install with: pip install -U magic-pdf[full]"
                )

            # Find output directory (MinerU creates a subdirectory)
            output_dirs = list(Path(tmpdir).glob("*/auto"))
            if not output_dirs:
                output_dirs = list(Path(tmpdir).rglob("*.json"))
                if output_dirs:
                    with open(output_dirs[0]) as f:
                        return json.load(f)
                raise RuntimeError("MinerU produced no output")

            json_files = list(output_dirs[0].glob("*.json"))
            if not json_files:
                raise RuntimeError("No JSON output from MinerU")

            with open(json_files[0]) as f:
                return json.load(f)


# ─── Skeleton Builder ──────────────────────────────────────────

class SkeletonBuilder:
    """Builds a PaperSkeleton from parser output."""

    def __init__(self, parser: str = "mineru", language: str = "en"):
        self.parser_name = parser
        self.language = language
        if parser == "mineru":
            self._parser = MinerUParser(language=language)
        else:
            raise ValueError(f"Unsupported parser: {parser}. Available: mineru")

    def build(self, pdf_path: str | Path) -> PaperSkeleton:
        """Parse a PDF and build a PaperSkeleton."""
        raw = self._parser.parse(pdf_path)
        return self._raw_to_skeleton(raw, pdf_path)

    def build_from_dict(self, raw: dict[str, Any], pdf_path: str = "") -> PaperSkeleton:
        """Build a skeleton from pre-parsed data (for testing)."""
        return self._raw_to_skeleton(raw, pdf_path)

    def _raw_to_skeleton(self, raw: dict, pdf_path: str | Path = "") -> PaperSkeleton:
        """Convert raw parser output to PaperSkeleton."""
        skeleton = PaperSkeleton()

        # Extract metadata (parser-specific logic)
        if "title" in raw:
            skeleton.title = raw["title"]
        if "authors" in raw:
            skeleton.authors = [
                Author(name=a.get("name", ""), affiliation=a.get("affiliation", ""))
                for a in raw.get("authors", [])
            ]

        # Extract sections
        sections_raw = raw.get("sections", raw.get("doc_layout", []))
        section_texts: dict[str, str] = {}
        for i, sec in enumerate(sections_raw):
            title = sec.get("title", sec.get("heading", f"Section {i}"))
            stype = classify_section(title)
            sec_id = f"sec_{stype.value}_{i}"
            skeleton.sections.append(SectionInfo(
                id=sec_id,
                title=title,
                start_page=sec.get("page", 0),
                type=stype,
            ))
            text = sec.get("text", sec.get("content", ""))
            if text:
                section_texts[stype.value] = section_texts.get(stype.value, "") + "\n" + text

        skeleton.section_texts = section_texts

        # Extract figures
        for fig in raw.get("figures", []):
            skeleton.figures.append(FigureInfo(
                id=fig.get("id", fig.get("label", "")),
                image_path=fig.get("image_path", fig.get("img_path", "")),
                caption=fig.get("caption", ""),
                section_context=fig.get("section", ""),
            ))

        # Extract tables
        for tbl in raw.get("tables", []):
            skeleton.tables.append(TableInfo(
                id=tbl.get("id", tbl.get("label", "")),
                content_html=tbl.get("html", tbl.get("content", "")),
                caption=tbl.get("caption", ""),
            ))

        # Extract equations
        for eq in raw.get("equations", raw.get("formulas", [])):
            skeleton.equations.append(EquationInfo(
                id=eq.get("id", ""),
                latex=eq.get("latex", eq.get("content", "")),
                context=eq.get("context", ""),
            ))

        # Stats
        skeleton.num_experiments_estimated = self._estimate_experiments(skeleton)
        skeleton.total_pages = raw.get("total_pages", raw.get("num_pages", 0))

        return skeleton

    def _estimate_experiments(self, skeleton: PaperSkeleton) -> int:
        """Rough estimate of number of experiments from section structure."""
        methods_text = skeleton.section_texts.get("methods", "")
        lower = methods_text.lower()

        # Count occurrences of experiment markers
        markers = ["experiment 1", "experiment 2", "experiment 3",
                    "study 1", "study 2", "study 3",
                    "exp. 1", "exp. 2", "exp. 3"]
        count = sum(1 for m in markers if m in lower)
        return max(count, 1) if methods_text else 0
