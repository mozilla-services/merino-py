"""Manage files between Wikimedia exports and gcs bucket"""

import bz2
import logging
import re
from datetime import datetime as dt
from html.parser import HTMLParser
from typing import Generator, Optional, Pattern
from urllib.parse import unquote, urljoin
from merino.configs import settings


import requests
from google.cloud.storage import Blob, Client
from google.cloud.storage.fileio import BlobReader, BlobWriter

from merino.exceptions import FilemanagerError
from merino.jobs.wikipedia_indexer.utils import ProgressReporter
from merino.utils.wikipedia import WIKIMEDIA_REQUEST_HEADERS
from google.api_core.exceptions import GoogleAPIError


logger = logging.getLogger(__name__)

SUPPORTED_LANGUAGES = set(settings.suggest_supported_languages)

# Dated snapshot directories in the export listing, e.g. "20260816/".
DATE_DIR_PATTERN = re.compile(r"^(\d{8})/$")

# Wikimedia writes this marker only once every shard of an index has been published.
# A snapshot directory without it is still being built and must not be ingested.
SUCCESS_MARKER = "_SUCCESS"

# Timeout for directory listing requests. Dump downloads stream are not bounded here.
LISTING_TIMEOUT = 60


class DirectoryParser(HTMLParser):
    """Collect the percent-decoded hrefs from a directory listing."""

    file_paths: list[str]

    def __init__(self) -> None:
        super().__init__()
        self.file_paths = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        """When the parser encounters an anchor, push its href into the list."""
        if tag == "a":
            for k, v in attrs:
                # Listings we read hold plain filenames, but Wikimedia percent-encodes
                # links to the "index_name=<wiki>_content/" directories, so decode either.
                if k == "href" and v is not None:
                    self.file_paths.append(unquote(v))


class WikipediaFilemanagerError(FilemanagerError):
    """Error during interaction with Wikipedia data."""


class FileManager:
    """Tools for managing files on Wikimedia export directory and copying into GCS"""

    base_url: str
    gcs_bucket: str
    object_prefix: str
    file_pattern: Pattern
    shard_pattern: Pattern
    client: Client
    language: str

    def __init__(
        self, gcs_bucket: str, gcs_project: str, export_base_url: str, language: str
    ) -> None:
        if language not in SUPPORTED_LANGUAGES:
            raise ValueError(
                f"Unsupported language '{language}'. Must be one of: {', '.join(SUPPORTED_LANGUAGES)}"
            )

        # Name of the reassembled dump as we store it on GCS. Upstream ships the export as
        # many shards, which we concatenate into a single object.
        self.file_pattern = re.compile(
            rf"(?:.*/|^){language}wiki-(\d+)-cirrussearch-content\.json\.bz2$"
        )
        # An individual upstream shard, e.g. "enwiki_content-20260816-00000.json.bz2".
        self.shard_pattern = re.compile(rf"^{language}wiki_content-(\d+)-(\d+)\.json\.bz2$")
        self.client = Client(gcs_project)
        self.base_url = export_base_url
        self.language = language
        if "/" in gcs_bucket:
            self.gcs_bucket, self.object_prefix = gcs_bucket.split("/", 1)
        else:
            self.gcs_bucket = gcs_bucket
            self.object_prefix = ""

    def get_latest_dump_shards(self, latest_gcs: Optional[Blob]) -> list[str]:
        """Find the shards of the latest complete export newer than the latest on GCS.

        Returns the shard URLs in order, or an empty list when GCS is already up to date.
        """
        last_gcs_date = self._parse_date(str(latest_gcs.name)) if latest_gcs else dt.min

        for snapshot_url, snapshot_date in self._list_snapshots():
            if snapshot_date <= last_gcs_date:
                # Snapshots are traversed newest first, so nothing older can qualify either.
                break
            try:
                shards = self._list_shards(snapshot_url)
            except requests.RequestException as e:
                logger.warning(f"Failed to list shards under {snapshot_url}: {e}")
                continue
            if shards:
                return shards

        return []

    def _list_snapshots(self) -> list[tuple[str, dt]]:
        """List the dated snapshot directories in the export listing, newest first."""
        snapshots: list[tuple[str, dt]] = []
        for href in self._list_hrefs(self.base_url):
            match = DATE_DIR_PATTERN.match(href)
            if not match:
                continue
            try:
                snapshot_date = dt.strptime(match.group(1), "%Y%m%d")
            except ValueError:
                logger.warning(f"Skipping unparseable snapshot directory: {href}")
                continue
            snapshots.append((urljoin(self.base_url, href), snapshot_date))

        snapshots.sort(key=lambda pair: pair[1], reverse=True)
        return snapshots

    def _list_shards(self, snapshot_url: str) -> list[str]:
        """List the ordered shard URLs for this language within a snapshot.

        Returns an empty list if the export is missing or not yet fully published.
        """
        index_url = urljoin(snapshot_url, f"index_name={self.language}wiki_content/")
        hrefs = self._list_hrefs(index_url)

        if SUCCESS_MARKER not in hrefs:
            logger.warning(
                "Skipping export without a success marker",
                extra={"url": index_url, "language": self.language},
            )
            return []

        matches = [m for m in (self.shard_pattern.match(h) for h in hrefs) if m]

        matches.sort(key=lambda m: int(m.group(2)))
        return [urljoin(index_url, m.group(0)) for m in matches]

    def _list_hrefs(self, url: str) -> list[str]:
        """Fetch a directory listing and return every href it contains."""
        resp = requests.get(url, timeout=LISTING_TIMEOUT, headers=WIKIMEDIA_REQUEST_HEADERS)  # nosec
        resp.raise_for_status()
        parser = DirectoryParser()
        parser.feed(resp.text)
        return parser.file_paths

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

    def stream_latest_dump_to_gcs(self, latest_gcs: Optional[Blob] = None) -> Optional[Blob]:
        """Stream the latest Wikimedia dump to GCS"""
        try:
            if not latest_gcs:
                latest_gcs = self.get_latest_gcs()
        except RuntimeError as e:
            logger.warning(
                f"No existing GCS file found, will stream latest from Wikimedia. Error: {e}"
            )
            latest_gcs = None

        shard_urls = self.get_latest_dump_shards(latest_gcs)
        logger.info(
            "latest_dump_shards",
            extra={"shard_count": len(shard_urls), "first_shard": shard_urls[:1]},
        )
        if shard_urls:
            self._stream_dump_to_gcs(shard_urls)
            # Recompute latest_gcs after upload
            latest_gcs = self.get_latest_gcs()
        else:
            logger.info("Currently up to date")

        return latest_gcs

    def _dump_blob_name(self, shard_url: str) -> str:
        """Build the GCS object name for the reassembled dump from a shard URL."""
        match = self.shard_pattern.match(shard_url.split("/")[-1])
        if not match:
            raise WikipediaFilemanagerError(f"Unrecognized shard name: {shard_url}")
        return f"{self.language}wiki-{match.group(1)}-cirrussearch-content.json.bz2"

    def _total_shard_size(self, shard_urls: list[str]) -> int:
        """Sum the sizes of the shards, for progress reporting. Returns 0 if unavailable."""
        total = 0
        for url in shard_urls:
            try:
                resp = requests.head(
                    url, timeout=LISTING_TIMEOUT, headers=WIKIMEDIA_REQUEST_HEADERS
                )  # nosec
                resp.raise_for_status()
                total += int(resp.headers.get("Content-Length", 0))
            except (requests.RequestException, ValueError) as e:
                logger.warning(f"Could not determine size of {url}: {e}")
                return 0
        return total

    def _stream_dump_to_gcs(self, shard_urls: list[str]) -> None:
        """Concatenate the upstream shards into a single blob on GCS.

        Each shard is an independent bzip2 stream. bzip2 permits streams to be
        concatenated, so the raw bytes are copied through verbatim and the result reads
        back as one continuous file. Nothing is decompressed or stored locally here.
        """
        # 40 MB chunk_size. This is the default Blob chunk size.
        # Having the same size will cause reads and writes to synchronize.
        chunk_size = 40 * 1024 * 1024
        name = "{}/{}".format(self.object_prefix, self._dump_blob_name(shard_urls[0]))
        blob = self.client.bucket(self.gcs_bucket).blob(name, chunk_size=chunk_size)
        try:
            content_len = self._total_shard_size(shard_urls)
            logger.info("Writing to GCS: gs://{}/{}".format(self.gcs_bucket, blob.name))
            logger.info("Total File Size: {}".format(content_len))
            logger.info("Shard count: {}".format(len(shard_urls)))

            reporter = (
                ProgressReporter(logger, "Copy", self.base_url, name, content_len)
                if content_len > 0
                else None
            )
            completed = 0
            writer: BlobWriter
            with blob.open("wb") as writer:
                for shard_url in shard_urls:
                    with requests.get(  # nosec
                        shard_url, stream=True, headers=WIKIMEDIA_REQUEST_HEADERS
                    ) as resp:
                        resp.raise_for_status()
                        for chunk in resp.iter_content(chunk_size=chunk_size):
                            completed += writer.write(chunk)
                            if reporter:
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
            with bz2.BZ2File(reader) as stream:
                for line in stream:
                    yield line
