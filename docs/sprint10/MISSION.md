# Sprint 10 — Paper-RAG Pipeline (12h autonomous session)

**Window:** 2026-04-17 21:00 KST → 2026-04-18 09:00 KST (12h, resumable after rate limits)
**Executor:** New Claude Code session, locally launched via `scripts/sprint10-kickoff.sh`
**Parent context:** Earlier session shipped Axon paper-coach PR [#33](https://github.com/Joonoh991119/csnl-command/pull/33). This session delivers the scientific RAG backend that plugs into the `paper-context.ts` hook.

You are working in a **fresh session without memory of the parent conversation**. Everything you need is in this document.

---

## Mission (one paragraph)

Execute the existing 4-stage roadmap in this repo (see `docs/roadmap.md`, `docs/schemas.md`) to ship a production-grade scientific-paper RAG pipeline: PDF → structured skeleton → argument extraction → figure deep-read → embeddings. Store in local Postgres 17 + pgvector. Borrow proven patterns from `Joonoh991119/ai-science-reading-tutor` (private, gh-accessible). Expose an HTTP endpoint that Axon's `electron/services/paper-context.ts` hook can call. Use **OpenRouter for heavy reasoning/VLM + local Ollama for cheap embeddings + fallback on rate limits**. Survive rate-limit outages via checkpoint → `ScheduleWakeup` → resume.

---

## Hard constraints

1. **No `ANTHROPIC_API_KEY` in code.** OpenRouter + Ollama only (env is in `~/Documents/Claude/Projects/_mcp-bundle/.env.master`).
2. **Local Postgres 17** (already running via `brew services`). Database name: `paper_rag`. Install `pgvector` if absent.
3. **TypeScript strict** in any Axon-facing bridge. Python 3.11+ strict typing (mypy) in the RAG pipeline.
4. **No AI-purple UI** if you touch renderer code (macOS system colors, WCAG AA).
5. **Commit convention:** `feat(rag): ...` / `fix(rag): ...`, trailer `Co-Authored-By: Claude <noreply@anthropic.com>`.
6. **PR 1개 lane 1개.** You open PRs against `deep-paper-reader/main` only — J's orchestrator session merges. Do NOT merge yourself.
7. **Do not touch** `/Volumes/CSNL_new/Memory/Papers/embedding_nemotron/` — reference only, older model. Your pipeline supersedes it.

---

## Resources

### MCP (pre-connected in this session — verify at Phase 0)
- `mcp__zotero__*` — Zotero desktop local HTTP MCP (full library, semantic_search, annotations). Needs Zotero app open.
- `mcp__csnl-ontology__*` or `csnl-ontology` stdio — existing RAG adapter at `~/Zotero/csnl-ontology`. **Reuse, don't duplicate.**
- `mcp__ollama__*` — local Ollama (gemma4:26b, qwen3.5:27b-q8_0, gemma3:12b, embedding models).
- `mcp__11ccd527-...__notion-*` — Notion (claude.ai OAuth) for research-page sync.
- `mcp__csnl-slack-bot__*` — Slack DM for heartbeat/alerts.
- `mcp__Desktop_Commander__*` — filesystem/process ops.

### Repos (borrow patterns, do NOT work inside)
- `Joonoh991119/ai-science-reading-tutor` (private) — `skills/paper-processor`, `skills/equation-parser`, `skills/rag-pipeline`, `skills/ontology-rag`, `skills/conversation-sim`, `agent_team/orchestrator.py`, `agent_team/rag_pipeline.py`
- `~/Projects/axon` — Axon app. Your bridge plugs into `electron/services/paper-context.ts`.
- `~/Zotero/csnl-ontology` — existing extractor + zotero_loader + ontology_builder. Extend, don't rewrite.

### Environment
- `.env.master` at `~/Documents/Claude/Projects/_mcp-bundle/.env.master` (already sourced by `~/.zshrc`)
  - ✅ `OPENROUTER_API_KEY`, `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN` populated
  - ❌ `GITHUB_TOKEN` empty in bundle but `gh` CLI is keychain-authenticated (works)
  - ❌ `ZOTERO_API_KEY` empty in bundle but Zotero MCP works without it (talks to desktop app)
- Postgres 17 running. Default user is your OS user; no password locally.
- `/Users/joonoh/Zotero/csnl-ontology/.venv/` — has existing Python env for ontology adapter.

### Test corpus
- `tests/test_corpus.md` — 10 pre-selected papers from Zotero.

---

## Phase plan (8 phases, ~12h total, all checkpointed)

Each phase writes `{"phase": N, "step": "...", "last_update": "..."}` to `.sprint10/checkpoint.json` after every committable unit. On rate-limit or crash, resume reads this file and jumps to the next step.

### Phase 0 — Bootstrap + MCP verification (30 min)
- Load env from `.env.master`. Confirm `$OPENROUTER_API_KEY` is set.
- Run `scripts/sprint10-env-check.sh` — it verifies Postgres is up, Zotero MCP responds on :23120, Ollama responds on :11434, csnl-ontology import works.
- Confirm `pgvector` is installed (`CREATE EXTENSION IF NOT EXISTS vector;`). If missing: `brew install pgvector` → `brew services restart postgresql@17`.
- Confirm `gh auth status` shows logged in as `Joonoh991119`.
- Commit `.sprint10/phase0-ready.md` with the verified inventory.

### Phase 1 — Repo scan + concrete roadmap commit (30 min)
- Read `docs/roadmap.md`, `docs/schemas.md`, `docs/prompt-templates.md`, `docs/model-comparison.md`, `src/*.py` to understand what's already coded vs. stubbed.
- Pull patterns from `ai-science-reading-tutor`:
  ```bash
  gh api repos/Joonoh991119/ai-science-reading-tutor/contents/skills/paper-processor > /tmp/pp.json
  gh api repos/Joonoh991119/ai-science-reading-tutor/contents/skills/rag-pipeline > /tmp/rp.json
  gh api repos/Joonoh991119/ai-science-reading-tutor/contents/agent_team/rag_pipeline.py > /tmp/arp.json
  ```
  Decode the `content` field (`base64 -d`) and study. Cite borrowed patterns in commit messages.
- Update `docs/roadmap.md` with a "Sprint 10 execution" subsection listing concrete tasks pulled from Phase A-D of the existing roadmap + new Postgres + Axon bridge.
- Commit.

### Phase 2 — Postgres schema + migrations (90 min)
- Design schema in `db/migrations/0001_init.sql`:
  - `papers` (id, doi, title, zotero_key, paper_type, parsed_at, status)
  - `paper_sections` (id, paper_id, section_type, title, text, start_page, ord)
  - `paper_figures` (id, paper_id, fig_id, caption, image_bytes, vlm_description, subfigure_of)
  - `paper_chunks` (id, paper_id, section_id, chunk_idx, text, token_count, kind {text|figure_desc|equation|table})
  - `paper_embeddings` (chunk_id PK, embedding vector(1024), model, generated_at) — adjust dim to chosen model
  - `paper_arguments` (id, paper_id, hypothesis, formal_prediction, methods_design, evidence_chain) — from Stage 2
  - `rag_queries` (id, query, retrieved_chunk_ids JSON, created_at) — for evaluation
- Use `psycopg[binary]` + `pgvector.psycopg` for Python client.
- Add `src/db.py` with connection pool + schema migration runner (idempotent).
- Write `tests/test_db_schema.py` — spins up schema, inserts a sample row, retrieves, drops.
- Commit.

### Phase 3 — Parser (PDF → PaperSkeleton) (3h)
- Stage 1 of existing roadmap. Implement `src/stage1_skeleton/parser.py`.
- **Primary VLM choice for figure description**: OpenRouter `qwen/qwen3-vl-8b` (fast, cheap). Fallback: Ollama `qwen3.5:27b-q8_0` (local, free).
- Parse via MinerU if installed; otherwise `pdfplumber` + heuristic section detection as MVP. Note the degraded path in a `LIMITATIONS.md`.
- Store results into `papers`, `paper_sections`, `paper_figures`.
- Prompt patterns: study `ai-science-reading-tutor/skills/paper-processor/` + `equation-parser/`. Especially the figure-caption linking logic and the "skeleton scan in 30s" structured output.
- Smoke test on 3 papers from `tests/test_corpus.md`. Target: <60s per paper (not 30s — we don't have full MinerU).
- Commit.

### Phase 4 — Embedding pipeline (2h)
- Implement `src/embeddings/multi_level.py` (chunk → embed → pgvector).
- **Embedding models** (in priority order):
  1. OpenRouter `openai/text-embedding-3-large` (3072-dim, high quality) — primary for paper chunks.
  2. OpenRouter `cohere/embed-multilingual-v3.0` (1024-dim) — fallback for Korean annotations.
  3. Local Ollama `nomic-embed-text` (768-dim) — rate-limit fallback.
  - Normalize dimension per `paper_embeddings.model`; store one model family per paper to avoid mixed-dim queries.
- Chunking strategy: section-aware, ~500 tokens with 50 token overlap; figure captions + VLM description are their own chunks (kind=figure_desc).
- Batch ingest with backoff on 429. On 3 consecutive 429s → switch to Ollama fallback and log the transition to `.sprint10/session-log.md`.
- Smoke test: embed the 3 parsed papers, verify cosine-sim on 5 sample queries returns expected papers.
- Commit.

### Phase 5 — RAG search API + Zotero MCP integration (2h)
- `src/api/server.py` — FastAPI on `127.0.0.1:8787`:
  - `POST /retrieve` → `{query, topK, filters}` → `[{source, title, snippet, score}]` (matches the shape `paper-context.ts` expects).
  - `POST /ingest` → `{zotero_key}` → triggers Phase 3+4 for a single paper (for Axon's picker flow).
  - `GET /health`.
- Use `mcp__zotero__semantic_search` as a FALLBACK ranker (combine with pgvector via reciprocal rank fusion) — proves the value of Zotero's built-in index without duplicating it.
- Integrate with `csnl-ontology` adapter: on each query, also expand via its ontology terms (`from csnl_ontology.rag_adapter import ...`).
- Write 10+ query evaluation tests against `tests/test_corpus.md` — at least 80% top-3 precision.
- Commit.

### Phase 6 — Axon bridge (1h)
- In the Axon worktree `~/Projects/axon/`, create a new branch `feat/paper-rag-bridge`.
- Modify `electron/services/paper-context.ts`:
  - New env var: `PAPER_RAG_URL=http://127.0.0.1:8787` (replaces the old `PAPER_EMBEDDINGS_ENDPOINT`).
  - When set, POST `/retrieve` and map the response shape 1:1 to `ContextPassage[]`.
  - Keep the old endpoint hook for backward compatibility (behind the same env gate).
- Add one test asserting the new endpoint path produces correctly shaped passages.
- Open PR against `axon/main` with title `feat(paper-coach): wire paper-rag pipeline to paper-context hook`. Do NOT merge.
- Commit.

### Phase 7 — Smoke test end-to-end (1h)
- Run: open Axon dev build (`npm run dev` in the axon worktree) → start paper coach → pick a paper → confirm the coach's LLM user message now includes `관련 랩 지식 (top-N):` block sourced from Postgres.
- Document the observed behavior + any rough edges in `docs/sprint10/E2E_SMOKE_REPORT.md`.
- Commit.

### Phase 8 — Final PRs + Slack DM to J (30 min)
- Open PR against `deep-paper-reader/main` bundling all Sprint 10 commits. Title: `feat(sprint10): paper-rag pipeline on postgres+pgvector with axon bridge`. Reference axon PR #33.
- Post a Slack DM to J via `mcp__csnl-slack-bot__csnl_send_dm` summarizing: PRs opened, tests passing, what's still stubbed, any rate-limit interruptions encountered, current time vs. planned 12h budget.
- Update `.sprint10/checkpoint.json` to `{"phase": 8, "step": "done"}`.

---

## Rate-limit protocol (critical)

**Triggers:** OpenRouter HTTP 429, Claude API usage limit, timeout clusters (>3 in 10 min).

**Response:**
1. Save checkpoint immediately:
   ```json
   {
     "phase": <current>,
     "step": "<granular step id>",
     "retry_count": <n+1>,
     "reason": "<short>",
     "last_update": "<ISO>",
     "next_action": "<what to do when we resume>"
   }
   ```
2. Append to `.sprint10/session-log.md`: `[<ISO>] Phase N: <reason>. Next action: <...>`.
3. **If Anthropic API limit:** use `ScheduleWakeup(delaySeconds=1800, prompt="/loop resume from .sprint10/checkpoint.json per docs/sprint10/MISSION.md", reason="rate-limited, resuming in 30 min")`.
4. **If OpenRouter only:** switch the current phase's calls to the Ollama fallback model and continue (no sleep needed). Log the model swap.
5. **If retry_count ≥ 4** on the same step: drop to a stub for that step, mark `degraded: true` in checkpoint, and proceed to the next phase. Sprint 10 ships even if imperfect.

**Cache warmth note:** prefer `delaySeconds` values either under 270s (stay in cache) or over 1200s (commit to a real pause). Never pick 300s.

---

## Session-log convention

Write to `.sprint10/session-log.md`, append-only, one line per event:

```
[2026-04-17T21:05:00+09:00] Phase 0 start
[2026-04-17T21:22:00+09:00] Phase 0 done — all MCP verified, pgvector installed
[2026-04-17T21:55:00+09:00] Phase 1 done — borrowed 3 patterns from ai-science-reading-tutor
[2026-04-17T23:40:00+09:00] Phase 3 rate-limit: OpenRouter 429 on qwen-vl. Switched to Ollama qwen3.5:27b-q8_0.
...
```

Keep it succinct. J reads this at 9am to understand what happened overnight.

---

## Definition of done (exit criteria)

- Postgres `paper_rag` database with schema + pgvector + 3+ papers ingested end-to-end.
- FastAPI RAG server returns relevant chunks on 3+ sample queries (at least 80% top-3 precision on test corpus).
- Axon `feat/paper-rag-bridge` PR open with passing test and correctly shaped passages.
- `deep-paper-reader/main` PR open with all Sprint 10 commits.
- Slack DM to J with summary.
- Checkpoint file shows `{"phase": 8, "step": "done"}`.

---

## If you are stuck

- Re-read this doc.
- Check `.sprint10/checkpoint.json` for your current state.
- Check `.sprint10/session-log.md` for what's already happened.
- `docs/roadmap.md` + `docs/schemas.md` have the detailed design.
- Model choices: `docs/model-comparison.md`.
- If truly blocked, leave a checkpoint with `blocked: true, reason: "..."`, post Slack DM to J, and stop cleanly.

Do not rabbit-hole. 12 hours is generous for Sprint 10 if you stay disciplined.
