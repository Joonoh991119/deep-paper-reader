-- Sprint 10 — Paper-RAG initial schema.
--
-- Design intent:
--   * Papers are first-class: ingesting a paper creates one `papers` row and
--     many `paper_sections`, `paper_figures`, `paper_chunks` rows.
--   * Chunks are the retrieval unit. Each chunk has an optional embedding
--     (nullable FK-less row in `paper_embeddings` keyed on chunk_id).
--   * Embeddings are dimension-tagged per model so we can swap embedders
--     without stale rows poisoning new queries. The query planner filters
--     by `model` column before doing the ANN scan.
--   * `paper_arguments` holds Stage-2 outputs (hypothesis/methods/results)
--     so the tutor layer can surface them without re-parsing.
--   * `rag_queries` logs every retrieval for offline evaluation + drift
--     detection. Append-only.
--
-- Trade-offs:
--   * No JSONB on paper metadata — we keep a small set of typed columns
--     (doi, title, zotero_key, paper_type) plus a `raw_metadata` JSONB for
--     the long tail. Reduces schema churn while keeping hot columns indexed.
--   * Figures store binary image bytes in `image_bytea`. For >1GB corpora
--     this should move to object storage; at 10-100 papers it's fine local.

CREATE EXTENSION IF NOT EXISTS vector;

-- -------------------------------------------------------------------------
-- papers: one row per ingested paper
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS papers (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  zotero_key      TEXT UNIQUE,
  doi             TEXT UNIQUE,
  title           TEXT NOT NULL,
  authors         TEXT[] NOT NULL DEFAULT '{}',
  journal         TEXT,
  year            INTEGER,
  paper_type      TEXT CHECK (paper_type IN ('empirical','computational','review','methods','case_study','preprint','unknown')) DEFAULT 'unknown',
  abstract        TEXT,
  raw_metadata    JSONB NOT NULL DEFAULT '{}'::jsonb,
  pdf_path        TEXT,
  status          TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','parsing','parsed','embedded','failed')),
  status_reason   TEXT,
  parsed_at       TIMESTAMPTZ,
  embedded_at     TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS papers_status_idx ON papers(status);
CREATE INDEX IF NOT EXISTS papers_zotero_key_idx ON papers(zotero_key);

-- -------------------------------------------------------------------------
-- paper_sections: structural sections of a paper
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS paper_sections (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  paper_id        UUID NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
  section_type    TEXT NOT NULL CHECK (section_type IN
                    ('abstract','introduction','background','related_work',
                     'methods','results','discussion','conclusion',
                     'references','supplementary','acknowledgments',
                     'data_availability','other')),
  title           TEXT,
  text            TEXT NOT NULL,
  start_page      INTEGER,
  ord             INTEGER NOT NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS paper_sections_paper_ord_idx ON paper_sections(paper_id, ord);

-- -------------------------------------------------------------------------
-- paper_figures: one row per (sub)figure
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS paper_figures (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  paper_id          UUID NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
  fig_id            TEXT NOT NULL,
  caption           TEXT,
  image_bytea       BYTEA,
  image_format      TEXT,
  vlm_description   TEXT,
  vlm_model         TEXT,
  subfigure_of      UUID REFERENCES paper_figures(id) ON DELETE CASCADE,
  section_context   TEXT,
  page              INTEGER,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (paper_id, fig_id)
);

CREATE INDEX IF NOT EXISTS paper_figures_paper_idx ON paper_figures(paper_id);

-- -------------------------------------------------------------------------
-- paper_chunks: retrieval unit. Section-scoped chunks + figure-caption chunks.
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS paper_chunks (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  paper_id          UUID NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
  section_id        UUID REFERENCES paper_sections(id) ON DELETE CASCADE,
  figure_id         UUID REFERENCES paper_figures(id) ON DELETE CASCADE,
  chunk_idx         INTEGER NOT NULL,
  text              TEXT NOT NULL,
  token_count       INTEGER,
  kind              TEXT NOT NULL CHECK (kind IN
                      ('text','figure_desc','equation','table','abstract','title_authors')),
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (paper_id, chunk_idx)
);

CREATE INDEX IF NOT EXISTS paper_chunks_paper_idx ON paper_chunks(paper_id);
CREATE INDEX IF NOT EXISTS paper_chunks_kind_idx ON paper_chunks(kind);

-- -------------------------------------------------------------------------
-- paper_embeddings: dimension-tagged per model to allow embedder swap
-- -------------------------------------------------------------------------
-- We store embeddings in separate column-per-dimension tables would be
-- cleaner, but pgvector supports only one `vector(N)` column per row.
-- Trade-off: we accept one embedding per (chunk_id, model) pair; if you
-- re-embed with a new model the old rows stay until you delete them.
CREATE TABLE IF NOT EXISTS paper_embeddings (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  chunk_id        UUID NOT NULL REFERENCES paper_chunks(id) ON DELETE CASCADE,
  model           TEXT NOT NULL,
  dim             INTEGER NOT NULL,
  embedding       vector NOT NULL,
  generated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (chunk_id, model)
);

-- HNSW index on cosine distance. Created per-dimension; the standard
-- practice is one partial index per model, but for <1M rows this lax
-- scan is fine.
CREATE INDEX IF NOT EXISTS paper_embeddings_model_idx ON paper_embeddings(model);
CREATE INDEX IF NOT EXISTS paper_embeddings_chunk_idx ON paper_embeddings(chunk_id);

-- -------------------------------------------------------------------------
-- paper_arguments: Stage 2 outputs (hypothesis/methods/results)
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS paper_arguments (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  paper_id              UUID NOT NULL UNIQUE REFERENCES papers(id) ON DELETE CASCADE,
  hypothesis            TEXT,
  formal_prediction     TEXT,
  methods_design        TEXT,
  evidence_chain        JSONB NOT NULL DEFAULT '[]'::jsonb,
  extracted_by_model    TEXT,
  extracted_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- -------------------------------------------------------------------------
-- rag_queries: append-only log for evaluation + drift detection
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS rag_queries (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  query_text          TEXT NOT NULL,
  retrieved_chunk_ids UUID[] NOT NULL DEFAULT '{}',
  topk                INTEGER,
  latency_ms          INTEGER,
  model_used          TEXT,
  client_tag          TEXT,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- -------------------------------------------------------------------------
-- auto-update updated_at on papers
-- -------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS papers_set_updated_at ON papers;
CREATE TRIGGER papers_set_updated_at
  BEFORE UPDATE ON papers
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
