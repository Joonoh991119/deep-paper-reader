# Sprint 10 — Research-background bulk ingest log

## Scope
Pre-seed the paper_rag DB with J's working research context so the Axon
paper-coach (and any downstream RAG consumer) has immediate relevance
without a per-session ingest. Autonomous run under "auto permission"
delegation from J on 2026-04-18.

## Sources
- **Zotero collections (4)**:
  - JOONOH > Computational Modeling > Efficient Coding (FIMEVXKF): 8 papers
  - JOONOH > Time Estimation (PT9VE66T): 11 papers
  - JOONOH > Magnitude (RE3HBQ58): 8 papers
  - JOONOH > Perceptual Bias (SITNFBAX): 7 papers
- **Notion research pages (3)**:
  - Research Background — Theoretical & Empirical Foundations
  - Time — Duration Perception History Effect
  - Time2Dist — Distribution Learning & Posterior Mapping

## Final inventory

| Metric | Value |
|---|---|
| Papers (total) | 40 |
| - Zotero PDFs (`paper_type=unknown`) | 37 |
| - Notion pages (`paper_type=notion_research`) | 3 |
| Sections | (see DB) |
| Chunks | 935 |
| Embeddings | 935 (all `ollama:bge-m3:latest`, 1024-dim) |

## Issues encountered + fixes

1. **NUL-byte PDF** (Lange et al. 2021, `XEFAXWV9`) — Postgres `text`
   columns reject 0x00. Fixed in `src/parser.py` by stripping NUL bytes
   from the raw page text once at source. Retry succeeded (9.4s).
2. **Paper-type CHECK constraint missed Notion** — initial schema
   enumerated only paper-ish types. Added migration
   `0002_paper_type_notion.sql` to extend the allowed set with
   `notion_research`, `slack_canvas`, `wiki`. Retry succeeded.

## Retrieval smoke (6 queries, top-3)

All 6 queries returned contextually relevant top-3 hits across the
mixed corpus (Zotero PDFs + Notion pages). Mixed Korean/English queries
also worked thanks to bge-m3's multilingual training.

- `Time2Dist 실험 설계 skewness 분포 학습` → Time2Dist page (0.734)
- `BLS Bayesian observer central tendency bias prior likelihood` → Wei&Stocker 2015 (0.642)
- `anti-Weber variability Fechner encoding skewed prior` → Research Background (0.682), Prat-Carrabin&Gershman 2025 (0.608)
- `serial dependence working memory perception mnemonic` → Park 2025 (0.721), Bliss 2017 (0.690), Ceylan 2023 (0.681)
- `efficient coding CDF Fisher information tuning` → Wei&Stocker 2016 monopoly
- `duration reproduction scaling history effect Korean 한국 시간 지각` → Cheng et al. 2024 (serial dependence in duration reproduction)

## Timings

- First paper (cold Ollama): ~60s (Park&Pillow 2024)
- Warm Ollama mean: 1-5s/paper (~1-3s embedding-dominant)
- 33-paper bulk run: ~3 minutes wall-clock
- 1-paper retry (NUL fix): 9.4s
- 3 Notion pages: 0.4-0.5s each (small documents)

## Files touched

- `db/migrations/0002_paper_type_notion.sql` (new)
- `src/parser.py` (NUL-byte strip, 1-line change)
- `src/text_ingest.py` (new — plain-text ingest helper)
- `scripts/sprint10_bulk_ingest.py` (new — curated Zotero list)
- `scripts/sprint10_notion_ingest.py` (new — Notion MCP page ingest)
- `.sprint10/bg_ingest_log.md` (this file)
