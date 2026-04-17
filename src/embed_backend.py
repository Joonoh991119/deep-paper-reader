"""Embedding backends — Ollama primary, OpenRouter fallback.

Design:
  * Local Ollama is primary (free, no rate limit, Korean-friendly with
    bge-m3). OpenRouter is used only when Ollama is unreachable OR when
    the caller explicitly asks for a specific cloud model.
  * Every embed call returns `(vector, model_tag)` so the caller can pass
    the exact model tag to `db.write_embedding`. That pins the dimension
    and prevents dim-mix pollution on the `paper_embeddings` table.
  * Batching is manual: callers pass a list of strings and receive a
    parallel list of vectors. We don't parallelise across threads because
    Ollama already serialises internally and the Mac Studio is single-GPU.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Sequence

import httpx

logger = logging.getLogger(__name__)


def _normalize_ollama_host(raw: str) -> str:
    """J's `.env.master` stores OLLAMA_HOST without the protocol prefix
    (`127.0.0.1:11434`). Normalize here so the same env var works whether
    or not a consumer prepends the scheme.
    """
    raw = (raw or "").strip().rstrip("/")
    if not raw:
        return "http://127.0.0.1:11434"
    if raw.startswith(("http://", "https://")):
        return raw
    return f"http://{raw}"


OLLAMA_HOST = _normalize_ollama_host(os.environ.get("OLLAMA_HOST", ""))
OLLAMA_EMBED_MODEL = os.environ.get("OLLAMA_EMBED_MODEL", "bge-m3:latest")

OPENROUTER_BASE = "https://openrouter.ai/api/v1"
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()
OPENROUTER_EMBED_MODEL = os.environ.get(
    "OPENROUTER_EMBED_MODEL", "openai/text-embedding-3-large"
)

DEFAULT_TIMEOUT_S = 60.0


@dataclass
class EmbedResult:
    vector: list[float]
    model: str


# ---- Ollama primary ---------------------------------------------------


def ollama_available() -> bool:
    try:
        r = httpx.get(f"{OLLAMA_HOST}/api/tags", timeout=5.0)
        return r.status_code == 200
    except Exception:
        return False


def embed_ollama(text: str, model: str = OLLAMA_EMBED_MODEL) -> EmbedResult:
    """Call Ollama's /api/embed endpoint.

    Ollama returns {"embeddings": [[...]]} for a single input. We normalise
    to a flat vector of floats so callers don't care about the wrapping
    shape. Raises `httpx.HTTPError` subclasses on network failure.
    """
    payload = {"model": model, "input": text}
    r = httpx.post(
        f"{OLLAMA_HOST}/api/embed", json=payload, timeout=DEFAULT_TIMEOUT_S
    )
    r.raise_for_status()
    body = r.json()
    vectors = body.get("embeddings")
    if not vectors or not isinstance(vectors, list):
        raise RuntimeError(f"Ollama returned no embeddings: {body!r}")
    first = vectors[0]
    if not isinstance(first, list) or not first:
        raise RuntimeError(f"Ollama returned empty embedding: {body!r}")
    return EmbedResult(vector=[float(x) for x in first], model=f"ollama:{model}")


# ---- OpenRouter fallback ---------------------------------------------


def openrouter_available() -> bool:
    return bool(OPENROUTER_KEY)


def embed_openrouter(text: str, model: str = OPENROUTER_EMBED_MODEL) -> EmbedResult:
    """OpenRouter /v1/embeddings (OpenAI-compatible)."""
    if not OPENROUTER_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is not set")
    headers = {
        "authorization": f"Bearer {OPENROUTER_KEY}",
        "content-type": "application/json",
        "HTTP-Referer": "https://github.com/Joonoh991119/deep-paper-reader",
        "X-Title": "deep-paper-reader",
    }
    payload = {"model": model, "input": text}
    r = httpx.post(
        f"{OPENROUTER_BASE}/embeddings",
        headers=headers,
        json=payload,
        timeout=DEFAULT_TIMEOUT_S,
    )
    r.raise_for_status()
    body = r.json()
    data = body.get("data") or []
    if not data:
        raise RuntimeError(f"OpenRouter returned no data: {body!r}")
    return EmbedResult(
        vector=[float(x) for x in data[0]["embedding"]],
        model=f"openrouter:{model}",
    )


# ---- Orchestration ----------------------------------------------------


def embed(
    text: str,
    prefer_local: bool = True,
    max_retries: int = 3,
    backoff_s: float = 1.5,
) -> EmbedResult:
    """Embed `text` with automatic fallback.

    When `prefer_local=True` (default) we try Ollama first; on network
    failure or consecutive rate limits, we fall through to OpenRouter.
    With `prefer_local=False` the order flips. Raises `RuntimeError` if
    every backend fails.
    """
    chain: list = []
    if prefer_local:
        chain.append(("ollama", embed_ollama))
        chain.append(("openrouter", embed_openrouter))
    else:
        chain.append(("openrouter", embed_openrouter))
        chain.append(("ollama", embed_ollama))

    last_err: Exception | None = None
    for name, fn in chain:
        for attempt in range(max_retries):
            try:
                return fn(text)
            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                if status == 429:
                    # Rate limited — exponential backoff on this backend,
                    # then give up and move to the next.
                    wait = backoff_s * (2**attempt)
                    logger.warning(
                        "[embed] %s 429, sleeping %.1fs (attempt %d/%d)",
                        name,
                        wait,
                        attempt + 1,
                        max_retries,
                    )
                    time.sleep(wait)
                    last_err = e
                    continue
                last_err = e
                break  # non-429 HTTP error → try the next backend
            except Exception as e:  # network, JSON, etc.
                last_err = e
                logger.warning("[embed] %s failed: %s", name, e)
                break
    raise RuntimeError(f"All embed backends failed. Last error: {last_err!r}")


def embed_many(
    texts: Sequence[str],
    prefer_local: bool = True,
    max_retries: int = 3,
) -> list[EmbedResult]:
    """Batch wrapper — sequential, since Ollama handles one request at a
    time and parallelising OpenRouter too aggressively just gets us 429'd.
    """
    out: list[EmbedResult] = []
    for i, t in enumerate(texts):
        out.append(embed(t, prefer_local=prefer_local, max_retries=max_retries))
        if (i + 1) % 10 == 0:
            logger.info("[embed] %d/%d done", i + 1, len(texts))
    return out
