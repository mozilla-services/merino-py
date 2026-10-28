"""Generate the Wikipedia article blocklist from the export and the category blocklist"""

import csv
import io
import json
import logging
from itertools import islice
from typing import Any

from merino.jobs.wikipedia_indexer.filemanager import FileManager
from merino.jobs.wikipedia_indexer.indexer import REDIRECT_PAGE_TYPE
from merino.jobs.wikipedia_indexer.utils import ProgressReporter

logger = logging.getLogger(__name__)

CSV_HEADER = ["title", "qid"]


class ArticleBlocklistGenerator:
    """Build a blocklist of the articles in a Wikipedia export that belong to a blocked category"""

    category_blocklist: set[str]
    file_manager: FileManager

    def __init__(self, category_blocklist: set[str], file_manager: FileManager):
        self.category_blocklist = category_blocklist
        self.file_manager = file_manager

    def generate(self, total_docs: int) -> str:
        """Stream the latest export from GCS and return the article blocklist as CSV.

        Each row holds the article title and its Wikidata QID (`wikibase_item`).
        Raises a `RuntimeError` if no export is available or no article is blocked.
        """
        latest = self.file_manager.get_latest_gcs()
        if latest is None:
            raise RuntimeError(f"No exports available on GCS for {self.file_manager.language}")

        logger.info("Start generating article blocklist", extra={"export": latest.name})
        reporter = ProgressReporter(logger, "Generating", latest.name, "csv", total_docs)

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(CSV_HEADER)

        scanned = 0
        blocked = 0
        gcs_stream = self.file_manager.stream_from_gcs(latest)
        # The export is a sequence of pairs of (`operator`, `document`) lines,
        # only the document is needed here.
        while pair := tuple(islice(gcs_stream, 2)):
            _, document = pair
            doc = json.loads(document)
            scanned += 1

            if self._should_block(doc):
                writer.writerow([doc.get("title", ""), doc.get("wikibase_item", "")])
                blocked += 1

            reporter.report(scanned)

        logger.info(
            "Completed generating article blocklist",
            extra={"export": latest.name, "scanned": scanned, "blocked": blocked},
        )
        # An empty blocklist most likely means the export or the category blocklist
        # changed shape. Fail rather than replace the last good blocklist.
        if blocked == 0:
            raise RuntimeError(f"No articles matched the category blocklist in {latest.name}")
        return output.getvalue()

    def _should_block(self, doc: dict[str, Any]) -> bool:
        """Return True if the document is an article in at least one blocked category."""
        if doc.get("page_type") == REDIRECT_PAGE_TYPE:
            return False
        return not self.category_blocklist.isdisjoint(doc.get("category", []))
