"""Text ingest — Notion pages and other non-PDF sources.

Takes a title + raw text and runs the same chunker / embedder pipeline
as `ingest.ingest_pdf`, minus the PyMuPDF layer. Useful for:
  * Notion research pages (background briefs, project definitions)
  * Markdown docs pulled from Slack canvases or the lab wiki
  * Zotero notes and annotations that aren't tied to a PDF

The resulting row in `papers` carries a synthetic key of the form
`notion:<page_id>` so it doesn't collide with Zotero item keys.
"""

from __future__ import annotations

import logging
from uuid import UUID

from . import db, embed_backend as embeddings, parser

logger = logging.getLogger(__name__)


def ingest_text(
    *,
    source_key: str,
    title: str,
    text: str,
    paper_type: str = "notion_research",
    authors: list[str] | None = None,
    raw_metadata: dict | None = None,
    prefer_local_embed: bool = True,
) -> UUID:
    """Ingest a plain-text document as a single-section paper.

    Chunks the text with the same paragraph-greedy chunker used for PDF
    sections, then embeds and persists. Idempotent on `source_key`
    (upsert by zotero_key column — same semantics).
    """
    if not text or not text.strip():
        raise ValueError("ingest_text: empty body")
    with db.connect() as conn:
        paper_row = db.Paper(
            id=UUID(int=0),
            zotero_key=source_key,
            doi=None,
            title=title.strip()[:500] or source_key,
            authors=authors or [],
            journal=None,
            year=None,
            paper_type=paper_type,
            abstract=None,
            raw_metadata=raw_metadata or {},
            pdf_path=None,
            status="parsing",
        )
        paper_id = db.upsert_paper(conn, paper_row)

        # One synthetic section covering the whole doc, then run the
        # paragraph chunker on it.
        section = parser.ParsedSection(
            section_type="other",
            title=title,
            text=text,
            start_page=1,
            ord=0,
        )
        section_id = db.insert_section(
            conn,
            db.Section(
                id=UUID(int=0),
                paper_id=paper_id,
                section_type=section.section_type,
                title=section.title,
                text=section.text,
                start_page=section.start_page,
                ord=section.ord,
            ),
        )
        chunks = parser.chunk_section(section, target_tokens=500, overlap_tokens=50)
        if not chunks:
            # fallback: single chunk containing everything
            chunks = [
                parser.ParsedChunk(
                    chunk_idx=0,
                    text=text[:8000],
                    token_count=parser.estimate_tokens(text[:8000]),
                    kind="text",
                    section_ord=0,
                    figure_fig_id=None,
                )
            ]
        chunk_ids: list[UUID] = []
        # Prepend a title_authors chunk so title-based retrieval still
        # works well even when the body is all about methodology.
        title_chunk = parser.ParsedChunk(
            chunk_idx=0,
            text=f"{title}\n{', '.join(authors or [])}".strip(),
            token_count=parser.estimate_tokens(title),
            kind="title_authors",
            section_ord=None,
            figure_fig_id=None,
        )
        for idx, c in enumerate([title_chunk, *chunks]):
            cid = db.insert_chunk(
                conn,
                db.Chunk(
                    id=UUID(int=0),
                    paper_id=paper_id,
                    section_id=section_id if c.kind != "title_authors" else None,
                    figure_id=None,
                    chunk_idx=idx,
                    text=c.text[:4000],
                    token_count=c.token_count,
                    kind=c.kind,
                ),
            )
            chunk_ids.append(cid)
        db.set_paper_status(conn, paper_id, "parsed")

    # Embed out-of-transaction.
    for cid in chunk_ids:
        with db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT text FROM paper_chunks WHERE id=%s", (cid,))
                row = cur.fetchone()
        if not row:
            continue
        try:
            result = embeddings.embed(row["text"], prefer_local=prefer_local_embed)
        except Exception as e:
            logger.error("embed failed for chunk %s: %s", cid, e)
            continue
        with db.connect() as conn:
            db.write_embedding(conn, cid, result.model, result.vector)
    with db.connect() as conn:
        db.set_paper_status(conn, paper_id, "embedded")
    return paper_id
