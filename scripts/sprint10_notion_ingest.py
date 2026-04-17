"""Ingest J's Notion research pages as background-context rows.

Reads the 3 priority pages from /tmp/sprint10_notion/ and inserts them
into the paper_rag DB via src.text_ingest.ingest_text. Each page gets
its own paper row with zotero_key = f'notion:{page_id}' so Notion and
Zotero keys never collide.

Extend by dropping more markdown files into /tmp/sprint10_notion/ with
the schema defined in NOTION_PAGES below.
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

from src import text_ingest


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("sprint10-notion")


# (page_id, display_title, path_under_/tmp/sprint10_notion)
NOTION_PAGES: list[tuple[str, str, str]] = [
    (
        "34172c9005d4816a8da7fcd66db430e6",
        "Research Background — Theoretical & Empirical Foundations",
        "research_background.md",
    ),
    (
        "32c72c9005d4812fb640d24d0d1465ef",
        "Time — Duration Perception History Effect",
        "time_project.md",
    ),
    (
        "32c72c9005d481769344c6df089163da",
        "Time2Dist — Distribution Learning & Posterior Mapping",
        "time2dist_project.md",
    ),
]

STAGING = Path("/tmp/sprint10_notion")


def main() -> int:
    ok = 0
    fail = 0
    for page_id, title, fname in NOTION_PAGES:
        path = STAGING / fname
        if not path.exists():
            log.warning("skip %s: staging file missing at %s", page_id, path)
            fail += 1
            continue
        body = path.read_text()
        t0 = time.time()
        try:
            paper_id = text_ingest.ingest_text(
                source_key=f"notion:{page_id}",
                title=title,
                text=body,
                paper_type="notion_research",
                authors=["Joonoh Park (JOP)", "CSNL"],
                raw_metadata={
                    "notion_page_id": page_id,
                    "notion_url": f"https://www.notion.so/{page_id}",
                    "source": "notion-mcp",
                    "kind": "research-background",
                },
            )
            log.info("ok %s → %s (%.1fs)", page_id, paper_id, time.time() - t0)
            ok += 1
        except Exception as e:
            log.error("fail %s: %s", page_id, e)
            fail += 1
    log.info("Done. ok=%d fail=%d", ok, fail)
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
