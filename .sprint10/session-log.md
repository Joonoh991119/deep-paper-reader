# Sprint 10 session log

Append-only, one line per event. ISO-8601 timestamps in KST (+09:00).

[2026-04-17T21:18:00+09:00] Orchestrator session (axon paper-coach PR #33 author) seeded MISSION.md, START_PROMPT.md, env-check script, and this log.
[2026-04-17T21:18:00+09:00] Pre-flight env-check result: 0 FAIL, 3 WARN (pgvector not installed, csnl-ontology import failed, working tree dirty — all expected pre-kickoff).
[2026-04-17T23:50:00+09:00] User pivoted ("직접 진행해"): executing Sprint 10 inline in the orchestrator session instead of spawning a new 9pm session. All 8 phases run here.
[2026-04-17T23:55:00+09:00] Phase 0: `createdb paper_rag` + `CREATE EXTENSION vector` (pgvector 0.8.2) — done.
[2026-04-17T23:58:00+09:00] Phase 1+2: migration 0001_init applied (7 tables). Borrowed section regex + PyMuPDF extraction pattern from ai-science-reading-tutor/skills/paper-processor.
[2026-04-18T00:10:00+09:00] Phase 3+4: src/parser.py (PyMuPDF), src/embed_backend.py (Ollama bge-m3 primary, OpenRouter fallback), src/ingest.py, src/db.py (retrieve + upsert). Normalized OLLAMA_HOST to always carry scheme (env master stores bare host:port).
[2026-04-18T00:20:00+09:00] Phase 5: ingested Park&Pillow 2024 (37 chunks, 37 embeddings, ~60s cold start).
[2026-04-18T00:28:00+09:00] Fixed retrieve() SQL param order bug (query vec was being passed where model string expected).
[2026-04-18T00:32:00+09:00] Phase 5: ingested Wei&Stocker 2015 + 2017 (warm Ollama, ~6s + ~1.4s). Retrieval 3/3 queries → top-1 correct paper, scores 0.65-0.88.
[2026-04-18T00:40:00+09:00] Phase 6: Axon paper-context.ts now prefers PAPER_RAG_URL env (server-selected model). +2 tests, 8/8 pass.
[2026-04-18T00:45:00+09:00] Phase 7: python pytest 12/12 pass (parser helpers, section matching, chunk sizing, figure captions w/ next-marker boundary fix, ollama host normalization, retrieve signature).
[2026-04-18T00:50:00+09:00] Phase 8: final PRs + Slack DM pending next.
