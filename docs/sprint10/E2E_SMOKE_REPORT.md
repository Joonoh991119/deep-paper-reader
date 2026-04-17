# Sprint 10 — End-to-end smoke report

**Session:** 2026-04-17 21:00 KST onward (same orchestrator session; no separate `/loop` kickoff was needed — user pivoted to "직접 진행해")
**Status:** pipeline end-to-end operational on 3 papers

## What was exercised

1. `createdb paper_rag` + `CREATE EXTENSION vector` (pgvector 0.8.2 via Homebrew).
2. Applied `db/migrations/0001_init.sql` (7 tables, pgvector column, trigger).
3. Ingested 3 papers from J's Zotero library:
   - Park & Pillow (2024) — Bayesian Efficient Coding — zotero `8IZV4BEV`
   - Wei & Stocker (2015) — Bayesian observer model constrained by efficient coding — zotero `XZPCXXP9`
   - Wei & Stocker (2017) — Lawful relation between perceptual bias and discriminability — zotero `H3QEESXZ`
4. Embedded with local Ollama `bge-m3:latest` (1024-dim), persisted to `paper_embeddings`.
5. Retrieval via `cosine (<=>) ` — 3 sample queries, top-3 results inspected.

## Observed numbers

```
 Park & Pillow    : 5 sections, 37 chunks, 37 embeddings (embedded in ~60s)
 Wei & Stocker 15 : parsed + embedded in ~6s
 Wei & Stocker 17 : parsed + embedded in ~1.4s
```

Second/third papers are dramatically faster because the bge-m3 model stayed warm in Ollama.

## Query precision (top-3)

| # | Query | Top-1 paper | Top-1 score | Relevance of top-3 |
|---|---|---|---|---|
| 1 | `efficient coding with prior and likelihood` | Bayesian Efficient Coding (title) | 0.686 | 3/3 relevant |
| 2 | `Fisher information and mutual information relationship` | Wei & Stocker 2015 (chunk) | 0.648 | 3/3 relevant |
| 3 | `perceptual bias discrimination threshold lawful relation` | Wei & Stocker 2017 (title) | 0.876 | 3/3 relevant |

Hit rate: 3/3 queries landed the canonically correct paper at top-1. Figure-caption chunks surface alongside body-text chunks, confirming multi-kind retrieval works.

## Known gaps (not blockers, documented)

- **No figure images stored.** `parse_pdf` populates `paper_figures.caption` but leaves `image_bytea = NULL`. Adding the PyMuPDF `page.get_pixmap()` path is a follow-up — it wasn't required for this RAG pass since chunks already contain the caption text.
- **No equation LaTeX.** PyMuPDF-only MVP. A MinerU install (`magic-pdf[full]`) would recover equations, but it's a 1+GB dependency and wasn't warranted for the test corpus.
- **Single embedding model only.** The `paper_embeddings` table supports multiple models per chunk, but the ingest always writes `ollama:bge-m3:latest`. OpenRouter fallback activates on Ollama outage per `embed_backend.embed`.
- **FastAPI server not stood up as a daemon.** `uvicorn src.api_server:app --port 8787` works for a manual smoke, but there's no launchd/plist yet. Axon bridge tests mock the endpoint.
- **`rag_queries` logging is on** for every `/retrieve` call — drift detection infra is ready; no dashboard/alert wired yet.
- **csnl-ontology fusion is NOT wired.** The MISSION.md listed it as a nice-to-have for ontology-term expansion; the bge-m3 retrieval alone is already at 100% top-1 on sample queries, so the added complexity was deferred.

## Axon bridge (Phase 6)

`electron/services/paper-context.ts` now prefers the `PAPER_RAG_URL` env var over the legacy `PAPER_EMBEDDINGS_ENDPOINT` + `PAPER_EMBEDDINGS_MODEL` pair. When `PAPER_RAG_URL` is set, the coach POSTs `{query, topK}` (no model) to `{url}/retrieve`. The server-selected embedding model is determined by the corpus.

Axon tests: +2 new cases (`8 passed` for paper-context.test.ts), typecheck clean on the axon node side.

## Definition-of-done checklist

- [x] Postgres `paper_rag` schema with pgvector extension.
- [x] ≥3 papers ingested end-to-end.
- [x] Semantic search returns relevant chunks for ≥3 queries at ≥80% top-3 precision (actual: 100% top-1).
- [x] Axon `feat/paper-rag-bridge` branch with new env var + test.
- [x] Python unit tests (12 cases, all passing).
- [ ] Two PRs opened (pending final commit + push — next step).
- [ ] Slack DM to J (pending).

## Files added/modified

**deep-paper-reader:**
```
 db/migrations/0001_init.sql         (new, 7 tables + pgvector + trigger)
 src/db.py                           (new)
 src/parser.py                       (new)
 src/embed_backend.py                (new; renamed from embeddings.py to avoid pkg collision)
 src/ingest.py                       (new)
 src/api_server.py                   (new)
 tests/test_sprint10.py              (new, 12 tests)
 docs/sprint10/E2E_SMOKE_REPORT.md   (this file)
 .sprint10/session-log.md            (appended)
 .sprint10/checkpoint.json           (updated to phase 8)
```

**axon (on branch `feat/paper-rag-bridge`, stacked on `feat/paper-reading-coach`):**
```
 electron/services/paper-context.ts       (+PAPER_RAG_URL path, +request shape switch)
 electron/services/paper-context.test.ts  (+2 tests)
```
