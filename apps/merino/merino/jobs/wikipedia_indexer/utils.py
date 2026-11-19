"""Utilities for Dynamic Wikipedia indexer job"""

import base64
import csv
from collections.abc import Iterable
from datetime import UTC, datetime
from io import StringIO
from logging import Logger

import requests

from merino.utils.gcs import initialize_storage_client

# Timeout for downloading the category blocklist.
BLOCKLIST_TIMEOUT = 60

# Default folder, under the article blocklist prefix, for the titles each indexer run blocked.
BLOCKED_TITLES_DIR = "blocked_titles"


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
    """Return the object name of the newest article blocklist under `prefix`.

    Leading and trailing slashes on `prefix` are ignored, so `exports/` and `exports` agree.
    """
    return f"{prefix.strip('/')}/{LATEST_ARTICLE_BLOCKLIST}"


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


def encode_offline_blocklist_title(title: str) -> str:
    """Encode a title the way the offline uploader's `dynamic_wikipedia_blocklist.csv` stores it.

    The title is snake cased (spaces become underscores, as in Wikipedia page view titles),
    casefolded to match the uploader's case-insensitive comparison, then base64 encoded.
    """
    return base64.b64encode(title.replace(" ", "_").casefold().encode("utf-8")).decode("ascii")


def build_blocked_titles_csv(titles: Iterable[str]) -> str:
    """Build a CSV of blocked titles consumable by the offline uploader.

    Matches the format of `dynamic_wikipedia_blocklist.csv`: a `title` header followed by one
    encoded title per row, deduplicated and in first-seen order.
    """
    encoded = dict.fromkeys(encode_offline_blocklist_title(title) for title in titles)
    output = StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["title"])
    writer.writerows([title] for title in encoded)
    return output.getvalue()


def upload_blocked_titles(
    titles: Iterable[str], gcs_bucket: str, destination: str, gcp_project: str, language: str
) -> str:
    """Upload the titles an indexer run blocked to GCS.

    Writes `{destination}/{language}-{timestamp}.csv`, then copies it to
    `{destination}/{language}-latest.csv` so each language keeps its own latest copy.
    Returns the name of the timestamped object.
    """
    folder = destination.strip("/")
    timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")

    client = initialize_storage_client(destination_gcp_project=gcp_project)
    bucket = client.bucket(gcs_bucket)
    blob = bucket.blob(f"{folder}/{language}-{timestamp}.csv")
    blob.upload_from_string(build_blocked_titles_csv(titles), content_type="text/csv")
    bucket.copy_blob(blob, bucket, f"{folder}/{language}-latest.csv")
    return str(blob.name)
