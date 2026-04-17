"""FastAPI RAG server.

Exposes a single HTTP surface Axon's `paper-context.ts` hook speaks to:

  POST /retrieve   — top-k relevant chunks for a free-text query
  POST /ingest     — trigger ingest + embed for a single PDF
  GET  /health     — readiness check (DB + Ollama reachable)

The response shape of /retrieve is 1:1 compatible with the
`ContextPassage[]` shape Axon expects (source/title/snippet/score).
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from . import db, embed_backend as embeddings, ingest

logger = logging.getLogger(__name__)

app = FastAPI(
    title="deep-paper-reader RAG",
    version="0.1.0",
    description="Scientific paper retrieval for Axon paper-coach and friends.",
)


class RetrieveRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=4000)
    topK: int = Field(default=6, ge=1, le=20)
    paper_ids: list[UUID] | None = None
    kinds: list[str] | None = None


class ContextPassage(BaseModel):
    source: str  # chunk_id (used as a stable external id)
    title: str
    snippet: str
    score: float
    paper_id: str
    kind: str


class RetrieveResponse(BaseModel):
    passages: list[ContextPassage]


class IngestRequest(BaseModel):
    pdf_path: str
    zotero_key: str | None = None
    doi: str | None = None


class IngestResponse(BaseModel):
    paper_id: str
    chunks: int
    embeddings: int


@app.get("/health")
def health() -> dict[str, Any]:
    """Simple readiness: can we reach DB + Ollama?"""
    db_ok = False
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            db_ok = cur.fetchone() is not None
    return {
        "ok": db_ok and embeddings.ollama_available(),
        "db": db_ok,
        "ollama": embeddings.ollama_available(),
        "openrouter_key_configured": embeddings.openrouter_available(),
    }


@app.post("/retrieve", response_model=RetrieveResponse)
def retrieve(req: RetrieveRequest) -> RetrieveResponse:
    """Embed the query + cosine-rank chunks against that embedding.

    The current pipeline uses ONE embedding model for everything — the
    first chunk's model tag becomes the retrieval model. That keeps dim
    consistent. Mixed-model corpora require a per-model fallback which
    we'll add once we observe it in the wild.
    """
    t0 = time.time()
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT model FROM paper_embeddings LIMIT 1"
            )
            row = cur.fetchone()
    if not row:
        raise HTTPException(
            status_code=503,
            detail="no embeddings in DB yet — ingest some papers first",
        )
    model_tag = row["model"]
    # Embed the query using the same backend that produced the corpus.
    prefer_local = model_tag.startswith("ollama:")
    result = embeddings.embed(req.query, prefer_local=prefer_local)
    with db.connect() as conn:
        hits = db.retrieve(
            conn,
            query_embedding=result.vector,
            model=result.model,
            top_k=req.topK,
            paper_ids=req.paper_ids,
            kinds=req.kinds,
        )
        # Log the query for offline evaluation.
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO rag_queries (query_text, retrieved_chunk_ids, topk, latency_ms, model_used, client_tag)
                VALUES (%s,%s,%s,%s,%s,%s)
                """,
                (
                    req.query,
                    [h.chunk_id for h in hits],
                    req.topK,
                    int((time.time() - t0) * 1000),
                    result.model,
                    "http-retrieve",
                ),
            )
    passages = [
        ContextPassage(
            source=str(h.chunk_id),
            title=h.paper_title,
            snippet=h.text[:1200],
            score=h.score,
            paper_id=str(h.paper_id),
            kind=h.kind,
        )
        for h in hits
    ]
    return RetrieveResponse(passages=passages)


@app.post("/ingest", response_model=IngestResponse)
def ingest_endpoint(req: IngestRequest) -> IngestResponse:
    """Synchronous ingest. Fine for the small 10-paper test corpus;
    production should move this to a queue but that's out of scope."""
    path = Path(req.pdf_path)
    if not path.exists():
        raise HTTPException(404, f"pdf not found: {req.pdf_path}")
    paper_id = ingest.ingest_pdf(
        path, zotero_key=req.zotero_key, doi=req.doi
    )
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS n FROM paper_chunks WHERE paper_id=%s",
                (paper_id,),
            )
            chunks_n = cur.fetchone()["n"]
            cur.execute(
                """
                SELECT COUNT(*) AS n FROM paper_embeddings pe
                  JOIN paper_chunks pc ON pc.id=pe.chunk_id
                 WHERE pc.paper_id=%s
                """,
                (paper_id,),
            )
            embeds_n = cur.fetchone()["n"]
    return IngestResponse(
        paper_id=str(paper_id),
        chunks=chunks_n,
        embeddings=embeds_n,
    )
