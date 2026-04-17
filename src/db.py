"""Postgres + pgvector client for the RAG pipeline.

All data access funnels through this module. Keeps connection pooling,
vector encoding/decoding, and migration application in one place so the
rest of the codebase can treat papers/chunks/embeddings as plain Python
dataclasses.
"""

from __future__ import annotations

import json
import logging
import os
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Sequence
from uuid import UUID

import psycopg
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row

logger = logging.getLogger(__name__)


# Default DSN — overridable via PAPER_RAG_DSN for CI / alternate DBs.
DEFAULT_DSN = os.environ.get("PAPER_RAG_DSN", "postgresql:///paper_rag")

MIGRATIONS_DIR = Path(__file__).parent.parent / "db" / "migrations"


@dataclass
class Paper:
    id: UUID
    zotero_key: str | None
    doi: str | None
    title: str
    authors: list[str] = field(default_factory=list)
    journal: str | None = None
    year: int | None = None
    paper_type: str = "unknown"
    abstract: str | None = None
    raw_metadata: dict[str, Any] = field(default_factory=dict)
    pdf_path: str | None = None
    status: str = "pending"
    status_reason: str | None = None


@dataclass
class Section:
    id: UUID
    paper_id: UUID
    section_type: str
    title: str | None
    text: str
    start_page: int | None
    ord: int


@dataclass
class Figure:
    id: UUID
    paper_id: UUID
    fig_id: str
    caption: str | None
    vlm_description: str | None
    page: int | None = None


@dataclass
class Chunk:
    id: UUID
    paper_id: UUID
    section_id: UUID | None
    figure_id: UUID | None
    chunk_idx: int
    text: str
    token_count: int | None
    kind: str  # 'text'|'figure_desc'|'equation'|'table'|'abstract'|'title_authors'


def get_dsn() -> str:
    return os.environ.get("PAPER_RAG_DSN", DEFAULT_DSN)


@contextmanager
def connect() -> Iterator[psycopg.Connection]:
    """Open a connection with pgvector registered and dict rows."""
    conn = psycopg.connect(get_dsn(), row_factory=dict_row)
    try:
        register_vector(conn)
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def apply_migrations(dsn: str | None = None) -> list[str]:
    """Idempotently apply every .sql file in db/migrations/ in lexical order.

    Returns the list of files applied. Safe to call on every startup: each
    migration uses `CREATE ... IF NOT EXISTS`, so repeat applications are
    no-ops. No migration-tracking table needed at this scale.
    """
    target_dsn = dsn or get_dsn()
    applied: list[str] = []
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    with psycopg.connect(target_dsn) as conn:
        with conn.cursor() as cur:
            for path in files:
                sql = path.read_text()
                logger.info("Applying migration %s", path.name)
                cur.execute(sql)
                applied.append(path.name)
        conn.commit()
    return applied


# ---- Paper CRUD -------------------------------------------------------

def upsert_paper(conn: psycopg.Connection, paper: Paper) -> UUID:
    """Insert or update by zotero_key (preferred) or doi. Returns the row id."""
    with conn.cursor() as cur:
        if paper.zotero_key:
            cur.execute(
                """
                INSERT INTO papers
                  (zotero_key, doi, title, authors, journal, year, paper_type,
                   abstract, raw_metadata, pdf_path, status)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (zotero_key) DO UPDATE SET
                  doi = EXCLUDED.doi,
                  title = EXCLUDED.title,
                  authors = EXCLUDED.authors,
                  journal = EXCLUDED.journal,
                  year = EXCLUDED.year,
                  paper_type = EXCLUDED.paper_type,
                  abstract = EXCLUDED.abstract,
                  raw_metadata = EXCLUDED.raw_metadata,
                  pdf_path = COALESCE(EXCLUDED.pdf_path, papers.pdf_path),
                  status = EXCLUDED.status
                RETURNING id
                """,
                (
                    paper.zotero_key,
                    paper.doi,
                    paper.title,
                    paper.authors,
                    paper.journal,
                    paper.year,
                    paper.paper_type,
                    paper.abstract,
                    json.dumps(paper.raw_metadata),
                    paper.pdf_path,
                    paper.status,
                ),
            )
        else:
            cur.execute(
                """
                INSERT INTO papers
                  (doi, title, authors, journal, year, paper_type,
                   abstract, raw_metadata, pdf_path, status)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING id
                """,
                (
                    paper.doi,
                    paper.title,
                    paper.authors,
                    paper.journal,
                    paper.year,
                    paper.paper_type,
                    paper.abstract,
                    json.dumps(paper.raw_metadata),
                    paper.pdf_path,
                    paper.status,
                ),
            )
        row = cur.fetchone()
        assert row is not None
        return row["id"]


def set_paper_status(
    conn: psycopg.Connection, paper_id: UUID, status: str, reason: str | None = None
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE papers SET status=%s, status_reason=%s WHERE id=%s",
            (status, reason, paper_id),
        )


def insert_section(conn: psycopg.Connection, s: Section) -> UUID:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO paper_sections
              (paper_id, section_type, title, text, start_page, ord)
            VALUES (%s,%s,%s,%s,%s,%s)
            RETURNING id
            """,
            (s.paper_id, s.section_type, s.title, s.text, s.start_page, s.ord),
        )
        row = cur.fetchone()
        assert row is not None
        return row["id"]


def insert_chunk(conn: psycopg.Connection, c: Chunk) -> UUID:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO paper_chunks
              (paper_id, section_id, figure_id, chunk_idx, text, token_count, kind)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (paper_id, chunk_idx) DO UPDATE SET
              text = EXCLUDED.text,
              token_count = EXCLUDED.token_count,
              kind = EXCLUDED.kind
            RETURNING id
            """,
            (
                c.paper_id,
                c.section_id,
                c.figure_id,
                c.chunk_idx,
                c.text,
                c.token_count,
                c.kind,
            ),
        )
        row = cur.fetchone()
        assert row is not None
        return row["id"]


def write_embedding(
    conn: psycopg.Connection,
    chunk_id: UUID,
    model: str,
    embedding: Sequence[float],
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO paper_embeddings (chunk_id, model, dim, embedding)
            VALUES (%s,%s,%s,%s)
            ON CONFLICT (chunk_id, model) DO UPDATE SET
              dim = EXCLUDED.dim,
              embedding = EXCLUDED.embedding,
              generated_at = now()
            """,
            (chunk_id, model, len(embedding), list(embedding)),
        )


@dataclass
class RetrievalHit:
    chunk_id: UUID
    paper_id: UUID
    paper_title: str
    text: str
    kind: str
    score: float


def retrieve(
    conn: psycopg.Connection,
    query_embedding: Sequence[float],
    model: str,
    top_k: int = 8,
    paper_ids: list[UUID] | None = None,
    kinds: list[str] | None = None,
) -> list[RetrievalHit]:
    """Cosine-similarity retrieval against chunks embedded by `model`.

    Pure vector scan for now — HNSW index will kick in automatically once
    the table grows past ~10k rows. For <1k rows the planner picks seq scan
    and it's faster that way.
    """
    # Build positional params in the exact SQL-placeholder order:
    #   1: SELECT score — query vector
    #   2: WHERE pe.model
    #   3: optional WHERE paper_ids
    #   4: optional WHERE kinds
    #   last-1: ORDER BY — query vector (repeated)
    #   last:   LIMIT
    qvec = list(query_embedding)
    where_sql = "pe.model = %s"
    params: list[Any] = [qvec, model]
    if paper_ids:
        where_sql += " AND pc.paper_id = ANY(%s)"
        params.append(paper_ids)
    if kinds:
        where_sql += " AND pc.kind = ANY(%s)"
        params.append(kinds)
    params.append(qvec)
    params.append(top_k)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT pc.id          AS chunk_id,
                   pc.paper_id    AS paper_id,
                   p.title        AS paper_title,
                   pc.text        AS text,
                   pc.kind        AS kind,
                   1 - (pe.embedding <=> %s::vector) AS score
              FROM paper_embeddings pe
              JOIN paper_chunks pc ON pc.id = pe.chunk_id
              JOIN papers p        ON p.id  = pc.paper_id
             WHERE {where_sql}
          ORDER BY pe.embedding <=> %s::vector ASC
             LIMIT %s
            """,
            params,
        )
        rows = cur.fetchall()
    return [
        RetrievalHit(
            chunk_id=r["chunk_id"],
            paper_id=r["paper_id"],
            paper_title=r["paper_title"],
            text=r["text"],
            kind=r["kind"],
            score=float(r["score"]),
        )
        for r in rows
    ]
