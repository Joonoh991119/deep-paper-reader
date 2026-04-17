"""End-to-end ingest: PDF → parsed → stored → embedded."""

from __future__ import annotations

import logging
from pathlib import Path
from uuid import UUID

from . import db, embed_backend as embeddings, parser

logger = logging.getLogger(__name__)


def ingest_pdf(
    pdf_path: str | Path,
    zotero_key: str | None = None,
    doi: str | None = None,
    title_override: str | None = None,
    prefer_local_embed: bool = True,
) -> UUID:
    """Parse + persist + embed one PDF.

    Returns the `papers.id` UUID. Safe to re-run: papers with a
    `zotero_key` are upserted in place. Chunks with the same
    `(paper_id, chunk_idx)` are updated; stale chunks from a previous
    ingest of the same paper are NOT cleaned up — call
    `reset_paper(paper_id)` first if you need a clean slate.
    """
    parsed = parser.parse_pdf(pdf_path)
    with db.connect() as conn:
        paper_row = db.Paper(
            id=UUID(int=0),  # ignored by upsert; upsert returns the real id
            zotero_key=zotero_key,
            doi=doi or parsed.doi,
            title=title_override or parsed.title,
            authors=parsed.authors,
            journal=None,
            year=parsed.year,
            paper_type="unknown",
            abstract=parsed.abstract,
            raw_metadata=parsed.raw_metadata,
            pdf_path=str(pdf_path),
            status="parsing",
        )
        paper_id = db.upsert_paper(conn, paper_row)
        # Persist sections (fresh — no per-section upsert since re-running
        # parser produces new ord values that match).
        section_ord_to_id: dict[int, UUID] = {}
        for s in parsed.sections:
            sid = db.insert_section(
                conn,
                db.Section(
                    id=UUID(int=0),
                    paper_id=paper_id,
                    section_type=s.section_type,
                    title=s.title,
                    text=s.text,
                    start_page=s.start_page,
                    ord=s.ord,
                ),
            )
            section_ord_to_id[s.ord] = sid
        # Persist chunks.
        chunk_ids: list[UUID] = []
        for c in parsed.chunks:
            section_id = (
                section_ord_to_id.get(c.section_ord)
                if c.section_ord is not None
                else None
            )
            cid = db.insert_chunk(
                conn,
                db.Chunk(
                    id=UUID(int=0),
                    paper_id=paper_id,
                    section_id=section_id,
                    figure_id=None,
                    chunk_idx=c.chunk_idx,
                    text=c.text,
                    token_count=c.token_count,
                    kind=c.kind,
                ),
            )
            chunk_ids.append(cid)
        db.set_paper_status(conn, paper_id, "parsed")
    # Embed out of the DB transaction so a long-running Ollama call
    # doesn't hold a write lock. Each embedding is written in its own
    # short-lived connection.
    _embed_paper_chunks(paper_id, prefer_local=prefer_local_embed)
    with db.connect() as conn:
        db.set_paper_status(conn, paper_id, "embedded")
    return paper_id


def _embed_paper_chunks(paper_id: UUID, prefer_local: bool = True) -> int:
    """Walk chunks for `paper_id`, embed each, persist. Returns count."""
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, text FROM paper_chunks WHERE paper_id=%s ORDER BY chunk_idx",
                (paper_id,),
            )
            rows = cur.fetchall()
    count = 0
    for row in rows:
        chunk_id = row["id"]
        text = row["text"]
        # Truncate extremely long chunks — Ollama bge-m3 supports up to
        # 8192 tokens but quality drops above ~2000 chars. Truncate to
        # 4000 chars as a safety margin.
        trimmed = text[:4000]
        try:
            result = embeddings.embed(trimmed, prefer_local=prefer_local)
        except Exception as e:  # fall through — skip + log
            logger.error("embed failed for chunk %s: %s", chunk_id, e)
            continue
        with db.connect() as conn:
            db.write_embedding(conn, chunk_id, result.model, result.vector)
        count += 1
    return count


def reset_paper(paper_id: UUID) -> None:
    """Delete every section/chunk/figure/embedding for a paper; keep the
    `papers` row itself so external references survive.
    """
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM paper_sections WHERE paper_id=%s", (paper_id,))
            cur.execute("DELETE FROM paper_chunks WHERE paper_id=%s", (paper_id,))
            cur.execute("DELETE FROM paper_figures WHERE paper_id=%s", (paper_id,))
            cur.execute(
                "UPDATE papers SET status='pending' WHERE id=%s", (paper_id,)
            )
