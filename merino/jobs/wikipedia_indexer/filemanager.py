"""Manage files between Wikimedia exports and gcs bucket"""

import logging
import re
from datetime import datetime as dt
from gzip import GzipFile
from html.parser import HTMLParser
from typing import Generator, Optional, Pattern
from urllib.parse import urljoin
from merino.configs import settings


import requests
from google.cloud.storage import Blob, Client
from google.cloud.storage.fileio import BlobReader, BlobWriter

from merino.exceptions import FilemanagerError
from merino.jobs.wikipedia_indexer.utils import ProgressReporter
from google.api_core.exceptions import GoogleAPIError


logger = logging.getLogger(__name__)

SUPPORTED_LANGUAGES = set(settings.suggest_supported_languages)


class DirectoryParser(HTMLParser):
    """Parse the directory listing to find the specified file."""

    filter: Pattern[str]
    file_paths: list[str]

    def __init__(self, filter_wildcard: Pattern[str]) -> None:
        super().__init__()
        self.file_paths = []
        self.filter = re.compile(filter_wildcard)

    def _is_href(self, k: str, v: str) -> bool:
        return k == "href" and re.search(self.filter, v) is not None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        """When the parser encounters a start tag check for Anchor and push into list."""
        if tag == "a":
            hrefs = [v for k, v in attrs if v is not None and self._is_href(k, v)]
            self.file_paths.extend(hrefs)


class WikipediaFilemanagerError(FilemanagerError):
    """Error during interaction with Wikipedia data."""


class FileManager:
    """Tools for managing files on Wikimedia export directory and copying into GCS"""

    base_url: str
    gcs_bucket: str
    object_prefix: str
    file_pattern: Pattern
    client: Client
    language: str

    def __init__(
        self, gcs_bucket: str, gcs_project: str, export_base_url: str, language: str
    ) -> None:
        if language not in SUPPORTED_LANGUAGES:
            raise ValueError(
                f"Unsupported language '{language}'. Must be one of: {', '.join(SUPPORTED_LANGUAGES)}"
            )

        self.file_pattern = re.compile(
            rf"(?:.*/|^){language}wiki-(\d+)-cirrussearch-content.json.gz"
        )
        self.client = Client(gcs_project)
        self.base_url = export_base_url
        self.language = language
        if "/" in gcs_bucket:
            self.gcs_bucket, self.object_prefix = gcs_bucket.split("/", 1)
        else:
            self.gcs_bucket = gcs_bucket
            self.object_prefix = ""

    def get_latest_dump(self, latest_gcs: Optional[Blob]) -> Optional[str]:
        """Find the latest export that's newer than the latest on GCS (if any)."""
        last_gcs_date = self._parse_date(str(latest_gcs.name)) if latest_gcs else dt.min

        # 1. Try current/
        try:
            resp = requests.get(self.base_url)  # nosec
            parser = DirectoryParser(self.file_pattern)
            parser.feed(str(resp.content))
            links = parser.file_paths
            if len(links) == 1:
                name = links[0]
                url = urljoin(self.base_url, name)
                link_date = self._parse_date(name)
                if link_date > last_gcs_date:
                    return url
        except Exception as e:
            logger.warning(f"Failed to fetch listing from {self.base_url}: {e}")

        # 2. Fallback to dated directory (bandaid)
        fallback_url = "https://dumps.wikimedia.org/other/cirrussearch/20251027/"
        try:
            resp = requests.get(fallback_url)  # nosec
            parser = DirectoryParser(self.file_pattern)
            parser.feed(str(resp.content))
            links = parser.file_paths
            if len(links) == 1:
                name = links[0]
                url = urljoin(fallback_url, name)
                link_date = self._parse_date(name)
                if link_date > last_gcs_date:
                    logger.info(f"Using bandaid fallback dump from {fallback_url}")
                    return url
        except Exception as e:
            logger.warning(f"Fallback fetch failed: {e}")

        return None

    def _parse_date(self, filename: str) -> dt:
        """Parse datestring out of filename"""
        date_match = re.match(self.file_pattern, filename)
        if date_match:
            try:
                return dt.strptime(date_match.group(1), "%Y%m%d")
            except ValueError:
                pass
        # return a zero date if nothing is found
        return dt(1, 1, 1)

    def get_latest_gcs(self) -> Blob:
        """Find the most recent file on GCS that matches the language-specific pattern"""
        bucket = self.client.bucket(self.gcs_bucket)
        blobs: list[Blob] = [
            b
            for b in bucket.list_blobs(prefix=self.object_prefix)
            if self.file_pattern.match(b.name)
        ]
        if not blobs:
            raise RuntimeError(f"No matching dump files found for pattern: {self.file_pattern}")

        blobs.sort(key=lambda b: self._parse_date(str(b.name)))
        return blobs[-1]

    def stream_latest_dump_to_gcs(self, latest_gcs: Optional[Blob] = None) -> Blob:
        """Stream the latest Wikimedia dump to GCS"""
        try:
            if not latest_gcs:
                latest_gcs = self.get_latest_gcs()
        except RuntimeError as e:
            logger.warning(
                f"No existing GCS file found, will stream latest from Wikimedia. Error: {e}"
            )
            latest_gcs = None

        latest_dump_url = self.get_latest_dump(latest_gcs)
        logger.info("latest_dump_url", extra={"ldurl": latest_dump_url})
        if latest_dump_url:
            self._stream_dump_to_gcs(latest_dump_url)
            # Recompute latest_gcs after upload
            latest_gcs = self.get_latest_gcs()
        else:
            logger.info("Currently up to date")

        return latest_gcs

    def _stream_dump_to_gcs(self, dump_url: str) -> None:
        """Write latest to GCS without storing locally"""
        # 40 MB chunk_size. This is the default Blob chunk size.
        # Having the same size will cause reads and writes to synchronize.
        chunk_size = 40 * 1024 * 1024
        name = "{}/{}".format(self.object_prefix, dump_url.split("/")[-1])
        blob = self.client.bucket(self.gcs_bucket).blob(name, chunk_size=chunk_size)
        try:
            with requests.get(dump_url, stream=True) as resp:  # nosec
                content_len = int(resp.headers.get("Content-Length", 0))
                resp.raise_for_status()
                logger.info("Writing to GCS: gs://{}/{}".format(self.gcs_bucket, blob.name))
                logger.info("Total File Size: {}".format(content_len))
                reporter = ProgressReporter(logger, "Copy", dump_url, name, content_len)
                writer: BlobWriter
                with blob.open("wb") as writer:
                    for chunk in resp.iter_content(chunk_size=chunk_size):
                        completed = writer.write(chunk)
                        reporter.report(completed)

        except Exception as e:
            logger.error(f"Unexpected error during GCS streaming for {name}: {e}")

            if blob.exists():
                try:
                    logger.info(f"Deleting partial upload: gs://{self.gcs_bucket}/{blob.name}")
                    blob.delete()
                    logger.info(f"Deleted partial upload: gs://{self.gcs_bucket}/{blob.name}")

                except GoogleAPIError as delete_error:
                    logger.error(f"Failed to delete partial upload: {delete_error}")
            raise WikipediaFilemanagerError("Failed to stream dump to GCS") from e

    def stream_from_gcs(self, blob: Blob) -> Generator:
        """Streaming reader from GCS"""
        reader: BlobReader
        with blob.open("rb") as reader:
            with GzipFile(fileobj=reader) as gz:
                for line in gz:
                    yield line
