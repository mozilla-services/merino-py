"""Utilities for Dynamic Wikipedia indexer job"""

import csv
from io import StringIO
from logging import Logger

import requests

from merino.utils.gcs import initialize_storage_client

# Timeout for downloading the category blocklist.
BLOCKLIST_TIMEOUT = 60


class ProgressReporter:
    """Report progress via logs"""

    logger: Logger
    action: str
    source: str
    destination: str
    total: int
    progress: int

    def __init__(self, logger: Logger, action: str, source: str, destination: str, total: int):
        self.logger = logger
        self.action = action
        self.source = source
        self.destination = destination
        self.total = total
        self.progress = 0

    def report(self, completed: int, blocked: int = 0):
        """Log the completed progress as it advances"""
        next_progress = round((completed + blocked) / self.total * 100)
        if next_progress != self.progress:
            self.progress = next_progress
            self.logger.info(
                f"{self.action} progress: {self.progress}%",
                extra={
                    "source": self.source,
                    "destination": self.destination,
                    "percent_complete": self.progress,
                    "completed": completed,
                    "total_size": self.total,
                    "blocked": blocked,
                },
            )


def create_blocklist(blocklist_file_url: str) -> set[str]:
    """Create the category blocklist from an external file url."""
    resp = requests.get(blocklist_file_url, timeout=BLOCKLIST_TIMEOUT)  # nosec
    resp.raise_for_status()
    csv_reader = csv.DictReader(StringIO(resp.text), delimiter=",")
    return set(row["name"] for row in csv_reader)


# Object name, under the destination prefix, of the newest article blocklist.
LATEST_ARTICLE_BLOCKLIST = "latest.csv"


def latest_article_blocklist_blob(prefix: str) -> str:
    """Return the object name of the newest article blocklist under `prefix`."""
    return f"{prefix}/{LATEST_ARTICLE_BLOCKLIST}"


def load_article_blocklist(gcs_bucket: str, prefix: str, gcp_project: str) -> set[str]:
    """Load the Wikidata QIDs of blocked articles from the newest article blocklist on GCS.

    Reads `{gcs_bucket}/{prefix}/latest.csv`, as written by the article blocklist job.
    Raises a `RuntimeError` if the blocklist holds no QIDs, rather than letting the
    indexer publish an unfiltered index.
    """
    blob_name = latest_article_blocklist_blob(prefix)
    client = initialize_storage_client(destination_gcp_project=gcp_project)
    text = client.bucket(gcs_bucket).blob(blob_name).download_as_text()
    qids = {row["qid"] for row in csv.DictReader(StringIO(text)) if row.get("qid")}
    if not qids:
        raise RuntimeError(f"Article blocklist at {gcs_bucket}/{blob_name} contains no QIDs")
    return qids
