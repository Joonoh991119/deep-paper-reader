"""Stage 1: Skeleton Scan — PDF to structured paper skeleton.

Supports two parsing backends:
1. MinerU (magic-pdf) — high quality, GPU accelerated
2. PyMuPDF fallback — no GPU needed, simpler extraction

MinerU output structure (magic-pdf -p file.pdf -o outdir -m auto):
  outdir/
    {pdf_stem}/
      auto/
        {pdf_stem}.md
        {pdf_stem}_content_list.json
        {pdf_stem}_middle.json
        images/
"""

from __future__ import annotations

import json
import logging
import os
import re
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
        "model", "analysis", "computational",
    ],
    SectionType.RESULTS: ["result", "results", "findings", "simulations"],
    SectionType.DISCUSSION: [
        "discussion", "general discussion", "conclusion", "concluding",
        "limitations", "future directions", "summary",
    ],
    SectionType.SUPPLEMENTARY: ["supplementary", "supplemental", "appendix", "supporting information"],
    SectionType.REFERENCES: ["reference", "references", "bibliography"],
}


def classify_section(title: str) -> SectionType:
    lower = title.lower().strip()
    for stype, keywords in _SECTION_KEYWORDS.items():
        for kw in keywords:
            if kw in lower:
                return stype
    return SectionType.OTHER


# ─── MinerU Parser ─────────────────────────────────────────────

class MinerUParser:
    def __init__(self, language: str = "en"):
        self.language = language

    def parse(self, pdf_path: str | Path, output_dir: str | Path | None = None) -> dict[str, Any]:
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        pdf_stem = pdf_path.stem
        use_temp = output_dir is None
        if use_temp:
            tmpdir = tempfile.mkdtemp(prefix="dpr_mineru_")
            output_dir = Path(tmpdir)
        else:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)

        cmd = [
            "magic-pdf",
            "-p", str(pdf_path),
            "-o", str(output_dir),
            "-m", "auto",
            "--lang", self.language,
        ]
        logger.info(f"Running MinerU: {' '.join(cmd)}")

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if result.returncode != 0:
                logger.error(f"MinerU stderr: {result.stderr[:1000]}")
                raise RuntimeError(f"MinerU failed (exit {result.returncode}): {result.stderr[:500]}")
        except FileNotFoundError:
            raise RuntimeError("magic-pdf not found. Install: pip install -U 'magic-pdf[full]'")

        # Find the auto output directory
        auto_dir = output_dir / pdf_stem / "auto"
        if not auto_dir.exists():
            # Try flexible matching: MinerU may sanitize the filename
            for candidate in output_dir.iterdir():
                if candidate.is_dir():
                    sub_auto = candidate / "auto"
                    if sub_auto.exists():
                        auto_dir = sub_auto
                        break
            else:
                # Last resort: find any .md file
                md_files = list(output_dir.rglob("*.md"))
                if md_files:
                    auto_dir = md_files[0].parent
                else:
                    all_files = list(output_dir.rglob("*"))
                    raise RuntimeError(
                        f"MinerU produced no recognizable output.\n"
                        f"Expected: {output_dir / pdf_stem / 'auto'}\n"
                        f"Found {len(all_files)} files: {[str(f) for f in all_files[:10]]}"
                    )

        logger.info(f"MinerU output found at: {auto_dir}")
        return self._parse_output(auto_dir, pdf_stem)

    def _parse_output(self, auto_dir: Path, pdf_stem: str) -> dict[str, Any]:
        result: dict[str, Any] = {
            "title": "", "authors": [], "sections": [],
            "figures": [], "tables": [], "equations": [],
            "total_pages": 0, "markdown": "",
        }

        # Read markdown
        md_files = list(auto_dir.glob("*.md"))
        if md_files:
            md_text = md_files[0].read_text(encoding="utf-8", errors="replace")
            result["markdown"] = md_text
            result["sections"] = self._parse_markdown_sections(md_text)
            result["title"] = self._extract_title(md_text)

        # Read content_list.json
        for cl_file in auto_dir.glob("*content_list.json"):
            try:
                content_list = json.loads(cl_file.read_text(encoding="utf-8"))
                self._extract_from_content_list(content_list, result, auto_dir)
            except Exception as e:
                logger.warning(f"content_list.json parse error: {e}")
            break

        # Read middle.json for page count
        for mid_file in auto_dir.glob("*middle.json"):
            try:
                middle = json.loads(mid_file.read_text(encoding="utf-8"))
                result["total_pages"] = len(middle.get("pdf_info", []))
            except Exception:
                pass
            break

        # Collect standalone images not already captured
        images_dir = auto_dir / "images"
        if images_dir.exists():
            existing_paths = {f.get("image_path", "") for f in result["figures"]}
            for img_file in sorted(images_dir.iterdir()):
                if img_file.suffix.lower() in (".png", ".jpg", ".jpeg"):
                    if str(img_file) not in existing_paths:
                        result["figures"].append({
                            "id": img_file.stem,
                            "image_path": str(img_file),
                            "caption": "",
                        })

        return result

    def _parse_markdown_sections(self, md_text: str) -> list[dict]:
        sections = []
        current_heading = ""
        current_content: list[str] = []

        for line in md_text.split("\n"):
            m = re.match(r"^(#{1,3})\s+(.+)$", line)
            if m:
                if current_heading or current_content:
                    sections.append({"title": current_heading, "text": "\n".join(current_content).strip()})
                current_heading = m.group(2).strip()
                current_content = []
            else:
                current_content.append(line)

        if current_heading or current_content:
            sections.append({"title": current_heading, "text": "\n".join(current_content).strip()})
        return sections

    def _extract_title(self, md_text: str) -> str:
        for line in md_text.split("\n"):
            m = re.match(r"^#\s+(.+)$", line)
            if m:
                return m.group(1).strip()
        for line in md_text.split("\n"):
            line = line.strip()
            if line and not line.startswith("!") and len(line) > 10:
                return line[:200]
        return ""

    def _extract_from_content_list(self, content_list: list, result: dict, auto_dir: Path):
        fig_counter = 0
        tbl_counter = 0
        for item in content_list:
            itype = item.get("type", "")
            if itype == "image":
                fig_counter += 1
                img_path = item.get("img_path", "")
                if img_path and not os.path.isabs(img_path):
                    img_path = str(auto_dir / img_path)
                result["figures"].append({
                    "id": f"Fig{fig_counter}",
                    "image_path": img_path,
                    "caption": item.get("img_caption", ""),
                })
            elif itype == "table":
                tbl_counter += 1
                result["tables"].append({
                    "id": f"Table{tbl_counter}",
                    "content": item.get("table_body", ""),
                    "caption": item.get("table_caption", ""),
                })
            elif itype == "equation":
                result["equations"].append({
                    "id": f"Eq{len(result['equations']) + 1}",
                    "latex": item.get("text", ""),
                })


# ─── PyMuPDF Fallback Parser ──────────────────────────────────

class PyMuPDFParser:
    def parse(self, pdf_path: str | Path) -> dict[str, Any]:
        import fitz
        pdf_path = Path(pdf_path)
        doc = fitz.open(str(pdf_path))

        full_text = ""
        figures: list[dict] = []
        img_counter = 0

        img_dir = pdf_path.parent / f"{pdf_path.stem}_images"

        for page_num, page in enumerate(doc):
            full_text += page.get_text("text") + "\n\n"
            for img_index, img in enumerate(page.get_images(full=True)):
                img_counter += 1
                xref = img[0]
                try:
                    pix = fitz.Pixmap(doc, xref)
                    if pix.n - pix.alpha > 3:
                        pix = fitz.Pixmap(fitz.csRGB, pix)
                    # Only save images above a minimum size (skip tiny icons)
                    if pix.width > 50 and pix.height > 50:
                        img_dir.mkdir(exist_ok=True)
                        img_path = img_dir / f"img_p{page_num}_{img_index}.png"
                        pix.save(str(img_path))
                        figures.append({
                            "id": f"Fig{img_counter}",
                            "image_path": str(img_path),
                            "caption": "",
                        })
                except Exception:
                    pass

        sections = self._split_sections(full_text)

        doc.close()
        return {
            "title": self._extract_title(full_text),
            "authors": [],
            "sections": sections,
            "figures": figures,
            "tables": [],
            "equations": [],
            "total_pages": len(doc) if hasattr(doc, '__len__') else 0,
            "markdown": full_text,
        }

    def _split_sections(self, text: str) -> list[dict]:
        pattern = r"\n([A-Z][A-Z\s]{2,50})\n|\n(\d+\.?\s+[A-Z][^\n]{3,80})\n"
        parts = re.split(pattern, text)
        sections = []
        current_title = ""
        current_text: list[str] = []

        for part in parts:
            if part is None:
                continue
            stripped = part.strip()
            is_heading = (
                (len(stripped) < 80 and stripped.upper() == stripped and len(stripped) > 3)
                or re.match(r"^\d+\.?\s+[A-Z]", stripped)
            )
            if is_heading:
                if current_title or current_text:
                    sections.append({"title": current_title, "text": "\n".join(current_text).strip()})
                current_title = stripped.title() if stripped.upper() == stripped else stripped
                current_text = []
            else:
                current_text.append(part)

        if current_title or current_text:
            sections.append({"title": current_title, "text": "\n".join(current_text).strip()})
        return sections if sections else [{"title": "", "text": text}]

    def _extract_title(self, text: str) -> str:
        for line in text.strip().split("\n")[:10]:
            line = line.strip()
            if len(line) > 10 and not line.startswith("http") and not re.match(r"^\d+$", line):
                return line[:200]
        return ""


# ─── Skeleton Builder ──────────────────────────────────────────

class SkeletonBuilder:
    def __init__(self, parser: str = "mineru", language: str = "en"):
        self.parser_name = parser
        self.language = language

    def build(self, pdf_path: str | Path) -> PaperSkeleton:
        pdf_path = Path(pdf_path)
        if self.parser_name == "mineru":
            try:
                raw = MinerUParser(language=self.language).parse(pdf_path)
            except RuntimeError as e:
                logger.warning(f"MinerU failed: {e}. Falling back to PyMuPDF.")
                raw = PyMuPDFParser().parse(pdf_path)
        elif self.parser_name == "pymupdf":
            raw = PyMuPDFParser().parse(pdf_path)
        else:
            raise ValueError(f"Unknown parser: {self.parser_name}")
        return self._raw_to_skeleton(raw, pdf_path)

    def _raw_to_skeleton(self, raw: dict, pdf_path: Path) -> PaperSkeleton:
        skeleton = PaperSkeleton()
        skeleton.title = raw.get("title", pdf_path.stem)

        section_texts: dict[str, str] = {}
        for i, sec in enumerate(raw.get("sections", [])):
            title = sec.get("title", f"Section {i}")
            stype = classify_section(title)
            skeleton.sections.append(SectionInfo(
                id=f"sec_{stype.value}_{i}",
                title=title,
                type=stype,
            ))
            text = sec.get("text", "")
            if text:
                key = stype.value
                section_texts[key] = section_texts.get(key, "") + "\n\n" + text
        skeleton.section_texts = section_texts

        # Extract abstract
        md = raw.get("markdown", "")
        if md:
            intro_pos = md.lower().find("introduction")
            if intro_pos > 100:
                candidate = md[:intro_pos].strip()
                if skeleton.title and candidate.startswith(skeleton.title):
                    candidate = candidate[len(skeleton.title):].strip()
                candidate = re.sub(r"^#+\s*Abstract\s*\n?", "", candidate, flags=re.IGNORECASE).strip()
                if len(candidate) > 50:
                    skeleton.abstract = candidate[:3000]

        for fig in raw.get("figures", []):
            skeleton.figures.append(FigureInfo(
                id=fig.get("id", ""),
                image_path=fig.get("image_path", ""),
                caption=fig.get("caption", ""),
                section_context=fig.get("section", ""),
            ))

        for tbl in raw.get("tables", []):
            skeleton.tables.append(TableInfo(
                id=tbl.get("id", ""),
                content_html=tbl.get("content", ""),
                caption=tbl.get("caption", ""),
            ))

        for eq in raw.get("equations", []):
            skeleton.equations.append(EquationInfo(
                id=eq.get("id", ""),
                latex=eq.get("latex", ""),
            ))

        skeleton.num_experiments_estimated = self._estimate_experiments(skeleton)
        skeleton.total_pages = raw.get("total_pages", 0)
        return skeleton

    def _estimate_experiments(self, skeleton: PaperSkeleton) -> int:
        combined = (
            skeleton.section_texts.get("methods", "") +
            skeleton.section_texts.get("results", "")
        ).lower()
        markers = [
            "experiment 1", "experiment 2", "experiment 3",
            "study 1", "study 2", "study 3",
            "simulation 1", "simulation 2",
        ]
        count = sum(1 for m in markers if m in combined)
        return max(count, 1) if combined.strip() else 0
