-- Sprint 10 research-background ingest — widen paper_type enum.
--
-- The 0001 schema hard-coded paper_type to paper-ish kinds only. Notion
-- research pages, Slack canvases, and wiki docs are also legitimate
-- context sources but don't fit any of those labels. Rebuild the CHECK
-- constraint with the new allowed values.

ALTER TABLE papers DROP CONSTRAINT IF EXISTS papers_paper_type_check;

ALTER TABLE papers ADD CONSTRAINT papers_paper_type_check
  CHECK (paper_type IN (
    'empirical',
    'computational',
    'review',
    'methods',
    'case_study',
    'preprint',
    'notion_research',
    'slack_canvas',
    'wiki',
    'unknown'
  ));
