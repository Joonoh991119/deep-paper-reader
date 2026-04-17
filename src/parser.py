"""PDF parser — Stage 1 (skeleton scan).

MVP using PyMuPDF (fitz). Splits a paper into structural sections,
extracts figure captions, and lays out `Chunk` records ready for
embedding. Figure image bytes are extracted but VLM description is
deferred (happens later in a separate stage only when network is
available).

Pattern credit: sections regex, figure-caption linking, and the PyMuPDF
page-dict walk all borrow from `Joonoh991119/ai-science-reading-tutor`
(skills/paper-processor/SKILL.md).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


SECTION_PATTERNS: list[tuple[str, str]] = [
    (r"^\s*abstract\s*$", "abstract"),
    (r"^\s*(?:\d+\.?\s*)?introduction\s*$", "introduction"),
    (r"^\s*(?:\d+\.?\s*)?background\s*$", "background"),
    (r"^\s*(?:\d+\.?\s*)?related\s+work\s*$", "related_work"),
    (r"^\s*(?:\d+\.?\s*)?(?:materials?\s+and\s+)?methods?\s*$", "methods"),
    (r"^\s*(?:\d+\.?\s*)?results?(?:\s+and\s+discussion)?\s*$", "results"),
    (r"^\s*(?:\d+\.?\s*)?discussion\s*$", "discussion"),
    (r"^\s*(?:\d+\.?\s*)?conclusions?\s*$", "conclusion"),
    (r"^\s*references?\s*$", "references"),
    (r"^\s*bibliography\s*$", "references"),
    (r"^\s*supplementary\s+(?:materials?|information)\s*$", "supplementary"),
    (r"^\s*acknowledgments?\s*$", "acknowledgments"),
    (r"^\s*(?:data|code)\s+availability\s*$", "data_availability"),
]

# Rough token count (1 token ≈ 4 chars English; Korean is ~2 chars/token).
# We use a simple char/4 heuristic for sizing — not accurate enough to
# bill, but good enough for chunk budgeting.
def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


CHUNK_TARGET_TOKENS = 500
CHUNK_OVERLAP_TOKENS = 50
FIGURE_CAPTION_RE = re.compile(
    r"(?mi)^\s*(Fig(?:\.|ure)?\s*\d+[a-z]?[\.\:]?)\s*(.*)$"
)


@dataclass
class ParsedSection:
    section_type: str
    title: str
    text: str
    start_page: int
    ord: int


@dataclass
class ParsedFigure:
    fig_id: str
    caption: str
    image_bytes: bytes | None
    image_format: str | None
    page: int


@dataclass
class ParsedChunk:
    chunk_idx: int
    text: str
    token_count: int
    kind: str
    section_ord: int | None  # points back to a ParsedSection by ord
    figure_fig_id: str | None


@dataclass
class ParsedPaper:
    title: str
    authors: list[str]
    abstract: str
    year: int | None
    doi: str | None
    sections: list[ParsedSection] = field(default_factory=list)
    figures: list[ParsedFigure] = field(default_factory=list)
    chunks: list[ParsedChunk] = field(default_factory=list)
    raw_metadata: dict[str, Any] = field(default_factory=dict)


# ---- Pure helpers (unit-tested in isolation) -------------------------


def match_section_heading(line: str) -> str | None:
    """Return the canonical section_type for a single-line heading, or None.

    Only hits when the line is *exactly* a heading (heading-like lines that
    carry body text on the same line aren't section boundaries — those are
    inline references like "See Methods"). The regexes all use `^...$` so
    trailing punctuation / body on the same line fails the match.
    """
    stripped = line.strip()
    if len(stripped) > 60:
        return None  # section headings are short
    for pattern, kind in SECTION_PATTERNS:
        if re.match(pattern, stripped, re.IGNORECASE):
            return kind
    return None


def split_text_into_sections(full_text: str) -> list[ParsedSection]:
    """Walk the paper text line by line. Flush a section every time we hit
    a heading line that matches one of the canonical section regexes.
    """
    lines = full_text.splitlines()
    sections: list[ParsedSection] = []
    current_type: str | None = None
    current_title: str | None = None
    current_buf: list[str] = []
    current_start_page = 1
    for line in lines:
        hit = match_section_heading(line)
        if hit is not None:
            if current_type is not None and current_buf:
                sections.append(
                    ParsedSection(
                        section_type=current_type,
                        title=current_title or current_type,
                        text="\n".join(current_buf).strip(),
                        start_page=current_start_page,
                        ord=len(sections),
                    )
                )
            current_type = hit
            current_title = line.strip()
            current_buf = []
        else:
            if current_type is None:
                # Pre-abstract preamble (title/authors); drop on the floor
                # unless someone asks for it.
                continue
            current_buf.append(line)
    if current_type is not None and current_buf:
        sections.append(
            ParsedSection(
                section_type=current_type,
                title=current_title or current_type,
                text="\n".join(current_buf).strip(),
                start_page=current_start_page,
                ord=len(sections),
            )
        )
    return sections


def chunk_section(
    section: ParsedSection,
    target_tokens: int = CHUNK_TARGET_TOKENS,
    overlap_tokens: int = CHUNK_OVERLAP_TOKENS,
    starting_idx: int = 0,
) -> list[ParsedChunk]:
    """Greedy paragraph-level chunker with a character-based approximation.

    Token budget = `target_tokens`. We accumulate paragraphs (split on blank
    lines) until the running estimate exceeds the budget; at that point we
    emit a chunk and carry the last `overlap_tokens` worth of text into the
    next chunk as context.
    """
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", section.text) if p.strip()]
    chunks: list[ParsedChunk] = []
    buf: list[str] = []
    buf_tokens = 0
    idx = starting_idx
    overlap_chars = overlap_tokens * 4
    for para in paragraphs:
        t = estimate_tokens(para)
        if buf_tokens + t > target_tokens and buf:
            joined = "\n\n".join(buf)
            chunks.append(
                ParsedChunk(
                    chunk_idx=idx,
                    text=joined,
                    token_count=estimate_tokens(joined),
                    kind="text" if section.section_type != "abstract" else "abstract",
                    section_ord=section.ord,
                    figure_fig_id=None,
                )
            )
            idx += 1
            tail = joined[-overlap_chars:] if overlap_chars > 0 else ""
            buf = [tail, para] if tail else [para]
            buf_tokens = estimate_tokens(tail) + t
        else:
            buf.append(para)
            buf_tokens += t
    if buf:
        joined = "\n\n".join(buf)
        chunks.append(
            ParsedChunk(
                chunk_idx=idx,
                text=joined,
                token_count=estimate_tokens(joined),
                kind="text" if section.section_type != "abstract" else "abstract",
                section_ord=section.ord,
                figure_fig_id=None,
            )
        )
    return chunks


def extract_figure_captions(full_text: str) -> list[tuple[str, str]]:
    """Pull out figure captions from the concatenated page text.

    Returns `[(fig_id, caption), ...]`. Caption is the first paragraph
    following the figure label up to the next blank line — approximate but
    good enough for downstream VLM grounding.
    """
    # Walk line-by-line; when we hit a figure marker, concatenate following
    # lines until we hit a blank line. We always strip the marker prefix
    # from the caption.
    out: list[tuple[str, str]] = []
    lines = full_text.splitlines()
    i = 0
    while i < len(lines):
        m = FIGURE_CAPTION_RE.match(lines[i])
        if m:
            fig_id = re.sub(r"\s+", "", m.group(1)).rstrip(".:")
            caption_lines = [m.group(2).strip()] if m.group(2) else []
            j = i + 1
            # Stop on blank line OR on the next figure marker — captions
            # for consecutive figures shouldn't bleed into each other even
            # when the PDF flattened them without whitespace.
            while j < len(lines) and lines[j].strip() and not FIGURE_CAPTION_RE.match(lines[j]):
                caption_lines.append(lines[j].strip())
                j += 1
            caption = " ".join(caption_lines).strip()
            if caption:
                out.append((fig_id, caption))
            i = j
        else:
            i += 1
    return out


# ---- PyMuPDF-based top-level parser ----------------------------------


def parse_pdf(pdf_path: str | Path) -> ParsedPaper:
    """Open `pdf_path`, extract text + metadata + figures, produce a
    ready-to-store `ParsedPaper`.

    For MVP we rely on PyMuPDF alone (no MinerU). That means we don't get
    tables-as-HTML, equation LaTeX, or layout-aware block detection. The
    chunker still produces reasonable retrieval units by falling back to
    paragraph splits.
    """
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(pdf_path)
    doc = fitz.open(str(path))
    try:
        meta = doc.metadata or {}
        title = (meta.get("title") or "").strip()
        authors_raw = (meta.get("author") or "").strip()
        authors = [a.strip() for a in re.split(r"[;,]", authors_raw) if a.strip()]
        year = None
        # Crude year extraction from creation date or subject metadata.
        m = re.search(r"(\d{4})", meta.get("creationDate") or "")
        if m:
            year = int(m.group(1))
        full_text_parts: list[str] = []
        for page in doc:
            full_text_parts.append(page.get_text("text"))
        full_text = "\n".join(full_text_parts)
        sections = split_text_into_sections(full_text)
        abstract = next(
            (s.text for s in sections if s.section_type == "abstract"),
            "",
        )
        figures_raw = extract_figure_captions(full_text)
        figures = [
            ParsedFigure(
                fig_id=fid,
                caption=cap,
                image_bytes=None,  # image extraction deferred — VLM stage can pull page.get_pixmap
                image_format=None,
                page=1,  # TODO: locate the page that contains the caption
            )
            for fid, cap in figures_raw
        ]
        # Chunk sections + figure captions.
        chunks: list[ParsedChunk] = []
        for s in sections:
            chunks.extend(chunk_section(s, starting_idx=len(chunks)))
        for f in figures:
            chunks.append(
                ParsedChunk(
                    chunk_idx=len(chunks),
                    text=f.caption,
                    token_count=estimate_tokens(f.caption),
                    kind="figure_desc",
                    section_ord=None,
                    figure_fig_id=f.fig_id,
                )
            )
        title_chunk_text = f"{title}\n{', '.join(authors)}"
        if title_chunk_text.strip():
            chunks.insert(
                0,
                ParsedChunk(
                    chunk_idx=0,
                    text=title_chunk_text,
                    token_count=estimate_tokens(title_chunk_text),
                    kind="title_authors",
                    section_ord=None,
                    figure_fig_id=None,
                ),
            )
            # reindex
            for i, c in enumerate(chunks):
                c.chunk_idx = i
        return ParsedPaper(
            title=title or path.stem.replace("_", " "),
            authors=authors,
            abstract=abstract,
            year=year,
            doi=None,
            sections=sections,
            figures=figures,
            chunks=chunks,
            raw_metadata={
                "fitz_metadata": {k: v for k, v in meta.items() if v},
                "page_count": len(doc),
            },
        )
    finally:
        doc.close()
