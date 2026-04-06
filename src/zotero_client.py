"""Zotero integration — fetch papers from user's Zotero library.

Uses the Zotero Web API to:
1. List papers in the library (or specific collection)
2. Download PDF attachments
3. Extract metadata (DOI, title, authors, journal, year)
4. Track which papers have been processed

Requires: pip install pyzotero
"""

from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ZoteroPaper:
    """Metadata for a paper in Zotero."""
    key: str  # Zotero item key
    title: str = ""
    authors: list[str] = field(default_factory=list)
    doi: str = ""
    journal: str = ""
    year: int = 0
    abstract: str = ""
    tags: list[str] = field(default_factory=list)
    pdf_path: str = ""  # Local path after download
    collections: list[str] = field(default_factory=list)


class ZoteroClient:
    """Interface to a user's Zotero library."""

    def __init__(
        self,
        library_id: str | None = None,
        api_key: str | None = None,
        library_type: str = "user",
        local_storage: str = "./zotero_pdfs/",
    ):
        self.library_id = library_id or os.getenv("ZOTERO_LIBRARY_ID", "")
        self.api_key = api_key or os.getenv("ZOTERO_API_KEY", "")
        self.library_type = library_type
        self.local_storage = Path(local_storage)
        self.local_storage.mkdir(parents=True, exist_ok=True)
        self._zot = None

        if not self.library_id or not self.api_key:
            logger.warning(
                "Zotero credentials not set. Set ZOTERO_LIBRARY_ID and ZOTERO_API_KEY "
                "environment variables, or pass them directly."
            )

    def _get_client(self):
        """Lazy-load pyzotero client."""
        if self._zot is None:
            try:
                from pyzotero import zotero
                self._zot = zotero.Zotero(
                    self.library_id, self.library_type, self.api_key
                )
            except ImportError:
                raise RuntimeError("Zotero requires: pip install pyzotero")
        return self._zot

    # ── List Papers ─────────────────────────────────────────────

    def list_papers(
        self,
        collection_key: str | None = None,
        limit: int = 50,
        item_type: str = "journalArticle || conferencePaper || preprint",
    ) -> list[ZoteroPaper]:
        """List papers from Zotero library.

        Args:
            collection_key: Optional collection to filter by.
            limit: Maximum number of papers to return.
            item_type: Zotero item type filter.

        Returns:
            List of ZoteroPaper with metadata (no PDFs downloaded yet).
        """
        zot = self._get_client()

        if collection_key:
            items = zot.collection_items(collection_key, limit=limit)
        else:
            items = zot.items(limit=limit, itemType=item_type)

        papers = []
        for item in items:
            data = item.get("data", {})
            if data.get("itemType") in ("attachment", "note"):
                continue

            # Extract authors
            authors = []
            for creator in data.get("creators", []):
                name = f"{creator.get('firstName', '')} {creator.get('lastName', '')}".strip()
                if name:
                    authors.append(name)

            # Extract year
            date_str = data.get("date", "")
            year = 0
            if date_str:
                import re
                year_match = re.search(r"(\d{4})", date_str)
                if year_match:
                    year = int(year_match.group(1))

            papers.append(ZoteroPaper(
                key=item.get("key", ""),
                title=data.get("title", ""),
                authors=authors,
                doi=data.get("DOI", ""),
                journal=data.get("publicationTitle", data.get("proceedingsTitle", "")),
                year=year,
                abstract=data.get("abstractNote", ""),
                tags=[t.get("tag", "") for t in data.get("tags", [])],
                collections=data.get("collections", []),
            ))

        logger.info(f"Found {len(papers)} papers in Zotero")
        return papers

    def list_collections(self) -> list[dict[str, str]]:
        """List all collections in the library."""
        zot = self._get_client()
        collections = zot.collections()
        return [
            {
                "key": c["key"],
                "name": c["data"].get("name", ""),
                "parent": c["data"].get("parentCollection", ""),
            }
            for c in collections
        ]

    # ── Download PDFs ───────────────────────────────────────────

    def download_pdf(self, paper: ZoteroPaper) -> str | None:
        """Download PDF attachment for a paper.

        Returns the local file path, or None if no PDF found.
        """
        zot = self._get_client()

        # Find attachment children
        children = zot.children(paper.key)
        pdf_attachment = None
        for child in children:
            data = child.get("data", {})
            if (
                data.get("itemType") == "attachment"
                and data.get("contentType") == "application/pdf"
            ):
                pdf_attachment = child
                break

        if pdf_attachment is None:
            logger.warning(f"No PDF attachment found for: {paper.title}")
            return None

        # Download
        attachment_key = pdf_attachment["key"]
        filename = pdf_attachment["data"].get("filename", f"{paper.key}.pdf")
        local_path = self.local_storage / filename

        if local_path.exists():
            logger.info(f"PDF already downloaded: {local_path}")
            paper.pdf_path = str(local_path)
            return str(local_path)

        try:
            # pyzotero dumps the file content
            zot.dump(attachment_key, str(local_path))
            logger.info(f"Downloaded: {local_path}")
            paper.pdf_path = str(local_path)
            return str(local_path)
        except Exception as e:
            logger.error(f"Failed to download PDF for {paper.title}: {e}")
            return None

    def download_all_pdfs(
        self,
        papers: list[ZoteroPaper],
        skip_existing: bool = True,
    ) -> list[ZoteroPaper]:
        """Download PDFs for all papers. Returns papers with pdf_path set."""
        downloaded = []
        for paper in papers:
            if skip_existing:
                # Check if already downloaded
                expected = self.local_storage / f"{paper.key}.pdf"
                if expected.exists():
                    paper.pdf_path = str(expected)
                    downloaded.append(paper)
                    continue

            path = self.download_pdf(paper)
            if path:
                downloaded.append(paper)

        logger.info(f"Downloaded {len(downloaded)}/{len(papers)} PDFs")
        return downloaded

    # ── Batch Processing ────────────────────────────────────────

    def get_unprocessed(
        self,
        papers: list[ZoteroPaper],
        output_dir: str = "./output",
    ) -> list[ZoteroPaper]:
        """Filter to papers that haven't been processed yet."""
        out = Path(output_dir)
        unprocessed = []
        for paper in papers:
            result_file = out / paper.key / "reading_result.yaml"
            if not result_file.exists():
                unprocessed.append(paper)
        return unprocessed


# ─── CLI Helper ─────────────────────────────────────────────────

def zotero_list_command():
    """CLI command to list papers in Zotero."""
    client = ZoteroClient()
    papers = client.list_papers(limit=20)
    for i, p in enumerate(papers, 1):
        authors_str = ", ".join(p.authors[:3])
        if len(p.authors) > 3:
            authors_str += " et al."
        print(f"{i:3d}. [{p.year}] {authors_str}")
        print(f"     {p.title}")
        print(f"     {p.journal} | DOI: {p.doi}")
        print()


def zotero_download_command(limit: int = 10):
    """CLI command to download PDFs from Zotero."""
    client = ZoteroClient()
    papers = client.list_papers(limit=limit)
    downloaded = client.download_all_pdfs(papers)
    print(f"\nDownloaded {len(downloaded)} PDFs to {client.local_storage}")
