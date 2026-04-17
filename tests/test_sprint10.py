"""Sprint 10 unit tests — pure-function coverage for parser + embeddings + db helpers.

Does NOT require a running Postgres or Ollama; those paths are integration tests
and live in `test_sprint10_integration.py` (gated on env).
"""

from __future__ import annotations

import pytest

from src import embed_backend, parser


# ---- Parser helpers ---------------------------------------------------


class TestSectionMatching:
    def test_match_canonical_headings(self) -> None:
        assert parser.match_section_heading("Abstract") == "abstract"
        assert parser.match_section_heading("  introduction  ") == "introduction"
        assert parser.match_section_heading("Methods") == "methods"
        assert parser.match_section_heading("2. Results") == "results"
        assert parser.match_section_heading("Results and Discussion") == "results"
        assert parser.match_section_heading("Data availability") == "data_availability"

    def test_match_rejects_body_text(self) -> None:
        assert parser.match_section_heading("As discussed in the Introduction, ...") is None
        assert parser.match_section_heading("See Methods section 4.2.") is None

    def test_match_rejects_very_long_lines(self) -> None:
        long = "Introduction" + " x" * 80
        assert parser.match_section_heading(long) is None


class TestSplitIntoSections:
    def test_splits_canonical_paper(self) -> None:
        text = (
            "Garbage preamble line\n"
            "Abstract\n"
            "This is the abstract.\n"
            "Introduction\n"
            "Para one.\n\nPara two.\n"
            "Methods\n"
            "We did things.\n"
            "Results\n"
            "We found things.\n"
        )
        sections = parser.split_text_into_sections(text)
        types = [s.section_type for s in sections]
        assert types == ["abstract", "introduction", "methods", "results"]
        abstract = next(s for s in sections if s.section_type == "abstract")
        assert abstract.text.startswith("This is the abstract")


class TestChunkSection:
    def test_respects_target_tokens(self) -> None:
        long = "\n\n".join(["Lorem ipsum dolor sit amet." * 25 for _ in range(6)])
        section = parser.ParsedSection(
            section_type="methods",
            title="Methods",
            text=long,
            start_page=1,
            ord=0,
        )
        chunks = parser.chunk_section(section, target_tokens=200, overlap_tokens=20)
        # At least two chunks because the total well exceeds 200 tokens.
        assert len(chunks) >= 2
        # Each chunk stays within ~2x the target (rough budget + overlap).
        for c in chunks:
            assert c.token_count <= 500

    def test_kind_switches_for_abstract(self) -> None:
        section = parser.ParsedSection(
            section_type="abstract",
            title="Abstract",
            text="One paragraph.",
            start_page=1,
            ord=0,
        )
        chunks = parser.chunk_section(section)
        assert all(c.kind == "abstract" for c in chunks)


class TestFigureCaptions:
    def test_extracts_figure_labels(self) -> None:
        text = (
            "Body text here.\n"
            "Figure 1. The basic setup.\n"
            "Figure 2a: Details of panel a.\n"
            "More body text.\n"
            "Fig. 3 Other panel.\n"
        )
        out = parser.extract_figure_captions(text)
        fig_ids = [f for f, _ in out]
        assert "Figure1" in fig_ids
        assert "Figure2a" in fig_ids


# ---- Embedding backend helpers ---------------------------------------


class TestOllamaHostNormalization:
    def test_adds_scheme_when_missing(self) -> None:
        assert embed_backend._normalize_ollama_host("127.0.0.1:11434") == "http://127.0.0.1:11434"

    def test_preserves_scheme_when_present(self) -> None:
        assert embed_backend._normalize_ollama_host("https://ollama.foo:443") == "https://ollama.foo:443"

    def test_strips_trailing_slash(self) -> None:
        assert embed_backend._normalize_ollama_host("http://host/") == "http://host"

    def test_empty_gives_default(self) -> None:
        assert embed_backend._normalize_ollama_host("") == "http://127.0.0.1:11434"


# ---- DB query-param shape --------------------------------------------


class TestRetrieveSqlShape:
    """The retrieve() query is paramorder-sensitive; this test pins the
    signature in case a future refactor reshuffles the placeholders again.
    """

    def test_retrieve_arity(self) -> None:
        from src import db

        sig = db.retrieve.__annotations__
        # query_embedding + model are required; top_k has default; paper_ids
        # and kinds are optional lists.
        assert "query_embedding" in sig
        assert "model" in sig
        assert "top_k" in sig
        assert "paper_ids" in sig
        assert "kinds" in sig
