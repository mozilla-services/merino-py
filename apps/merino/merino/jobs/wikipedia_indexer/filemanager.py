"""Manage files between Wikimedia exports and gcs bucket"""

import asyncio
import bz2
import logging
import re
import threading
from dataclasses import dataclass
from datetime import datetime as dt
from html.parser import HTMLParser
from typing import Generator, Optional, Pattern
from urllib.parse import unquote, urljoin
from merino.configs import settings


import requests
from google.cloud.storage import Blob, Client
from google.cloud.storage.fileio import BlobReader, BlobWriter
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from merino.exceptions import FilemanagerError
from merino.jobs.wikipedia_indexer.utils import ProgressReporter
from merino.utils.wikipedia import WIKIMEDIA_REQUEST_HEADERS


logger = logging.getLogger(__name__)

SUPPORTED_LANGUAGES = set(settings.suggest_supported_languages)

# Dated snapshot directories in the export listing, e.g. "20260816/".
DATE_DIR_PATTERN = re.compile(r"^(\d{8})/$")

# Wikimedia writes this marker only once every shard of an index has been published.
# A snapshot directory without it is still being built and must not be ingested.
SUCCESS_MARKER = "_SUCCESS"

# Timeout for directory listing and HEAD requests.
LISTING_TIMEOUT = 60

# (connect, read) for shard downloads.
SHARD_TIMEOUT = (10, 60)

# 40 MB, the default GCS blob chunk size. Using it for both the HTTP read and the blob
# write keeps reads and writes synchronized within a shard.
CHUNK_SIZE = 40 * 1024 * 1024

# Wikimedia rate limits downloads and caps them at 3 connections per IP
# See https://dumps.wikimedia.org/.
DOWNLOAD_CONCURRENCY = 3

# The date format shared by the upstream layout and our GCS object names.
DATE_FORMAT = "%Y%m%d"


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


@dataclass(frozen=True)
class Snapshot:
    """One dated export, as it is laid out on GCS.

    `name` keeps the `<lang>wiki-<date>-cirrussearch-content` shape that the previous
    single-object layout used, so it still works as the basis for the index name.
    """

    name: str
    date: dt
    prefix: str


class FileManager:
    """Tools for managing files on Wikimedia export directory and copying into GCS"""

    base_url: str
    gcs_bucket: str
    object_prefix: str
    snapshot_pattern: Pattern
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

        # The per-snapshot prefix holding a snapshot's shards on GCS.
        self.snapshot_pattern = re.compile(
            rf"(?:.*/|^)({language}wiki-(\d+)-cirrussearch-content)/"
        )
        # An individual upstream shard, e.g. "enwiki_content-20260816-00000.json.bz2".
        self.shard_pattern = re.compile(rf"^{language}wiki_content-(\d+)-(\d+)\.json\.bz2$")
        self.client = Client(gcs_project)
        self.base_url = export_base_url
        self.language = language
        self._http: requests.Session | None = None
        # Bytes copied so far in the current run, shared across the copy workers.
        self._copied = 0
        self._progress_lock = threading.Lock()
        if "/" in gcs_bucket:
            self.gcs_bucket, self.object_prefix = gcs_bucket.split("/", 1)
        else:
            self.gcs_bucket = gcs_bucket
            self.object_prefix = ""

    @property
    def session(self) -> requests.Session:
        """A pooled session for Wikimedia requests."""
        if self._http is None:
            session = requests.Session()
            session.headers.update(WIKIMEDIA_REQUEST_HEADERS)
            adapter = HTTPAdapter(
                pool_maxsize=DOWNLOAD_CONCURRENCY,
                max_retries=Retry(
                    total=5,
                    connect=5,
                    read=3,
                    backoff_factor=1.0,
                    status_forcelist=(429, 500, 502, 503, 504),
                    raise_on_status=False,
                ),
            )
            session.mount("https://", adapter)
            session.mount("http://", adapter)
            self._http = session
        return self._http

    def get_latest_dump_shards(self, latest_gcs: Optional[Snapshot]) -> list[str]:
        """Find the shards of the latest complete export newer than the latest on GCS.

        Returns the shard URLs in order, or an empty list when GCS is already up to date.
        """
        last_gcs_date = latest_gcs.date if latest_gcs else dt.min

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
                snapshot_date = dt.strptime(match.group(1), DATE_FORMAT)
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
        resp = self.session.get(url, timeout=LISTING_TIMEOUT)  # nosec
        resp.raise_for_status()
        parser = DirectoryParser()
        parser.feed(resp.text)
        return parser.file_paths

    def _upstream_size(self, shard_url: str) -> int:
        """Return the upstream size of a shard, or 0 when it cannot be determined."""
        try:
            resp = self.session.head(shard_url, timeout=LISTING_TIMEOUT)  # nosec
            resp.raise_for_status()
            return int(resp.headers.get("Content-Length", 0))
        except (requests.RequestException, ValueError) as e:
            logger.warning(f"Could not determine size of {shard_url}: {e}")
            return 0

    def snapshot_for(self, snapshot_date: dt) -> Snapshot:
        """Describe where a snapshot's shards live on GCS."""
        name = f"{self.language}wiki-{snapshot_date.strftime(DATE_FORMAT)}-cirrussearch-content"
        prefix = f"{self.object_prefix}/{name}" if self.object_prefix else name
        return Snapshot(name=name, date=snapshot_date, prefix=prefix)

    def _snapshot_from_shard_url(self, shard_url: str) -> Snapshot:
        """Derive the GCS snapshot a shard URL belongs to."""
        match = self.shard_pattern.match(shard_url.rsplit("/", 1)[-1])
        if not match:
            raise WikipediaFilemanagerError(f"Unrecognized shard name: {shard_url}")
        return self.snapshot_for(dt.strptime(match.group(1), DATE_FORMAT))

    def get_latest_gcs(self) -> Optional[Snapshot]:
        """Find the most recent complete snapshot on GCS for this language.

        Snapshots without a success marker are ignored
        """
        dates: list[dt] = []
        for blob in self.client.bucket(self.gcs_bucket).list_blobs(prefix=self.object_prefix):
            name = str(blob.name)
            if not name.endswith(f"/{SUCCESS_MARKER}"):
                continue
            match = self.snapshot_pattern.match(name)
            if not match:
                continue
            try:
                dates.append(dt.strptime(match.group(2), DATE_FORMAT))
            except ValueError:
                logger.warning(f"Skipping unparseable snapshot on GCS: {name}")

        return self.snapshot_for(max(dates)) if dates else None

    def list_gcs_shards(self, snapshot: Snapshot) -> list[Blob]:
        """List a snapshot's shard blobs on GCS, in shard order."""
        indexed: list[tuple[int, Blob]] = []
        for blob in self.client.bucket(self.gcs_bucket).list_blobs(prefix=f"{snapshot.prefix}/"):
            match = self.shard_pattern.match(str(blob.name).rsplit("/", 1)[-1])
            if match:
                indexed.append((int(match.group(2)), blob))
        indexed.sort(key=lambda pair: pair[0])
        return [blob for _, blob in indexed]

    async def stream_latest_dump_to_gcs(
        self, latest_gcs: Optional[Snapshot] = None
    ) -> Optional[Snapshot]:
        """Stream the latest Wikimedia dump to GCS"""
        if not latest_gcs:
            latest_gcs = self.get_latest_gcs()
            if not latest_gcs:
                logger.warning("No existing snapshot on GCS, will copy the latest from Wikimedia")

        shard_urls = self.get_latest_dump_shards(latest_gcs)
        logger.info(
            "latest_dump_shards",
            extra={"shard_count": len(shard_urls), "first_shard": shard_urls[:1]},
        )
        if shard_urls:
            await self._stream_dump_to_gcs(shard_urls)
            # Recompute latest_gcs after upload
            latest_gcs = self.get_latest_gcs()
        else:
            logger.info("Currently up to date")

        return latest_gcs

    async def _stream_dump_to_gcs(self, shard_urls: list[str]) -> None:
        """Copy the upstream shards to GCS, one object per shard.

        Shards are copied concurrently.
        """
        snapshot = self._snapshot_from_shard_url(shard_urls[0])
        sizes = {url: self._upstream_size(url) for url in shard_urls}
        total = sum(sizes.values())

        logger.info(f"Writing to GCS: gs://{self.gcs_bucket}/{snapshot.prefix}/")
        logger.info("Total File Size: {}".format(total))
        logger.info("Shard count: {}".format(len(shard_urls)))

        reporter = (
            ProgressReporter(logger, "Copy", self.base_url, snapshot.prefix, total)
            if total > 0
            else None
        )
        semaphore = asyncio.Semaphore(DOWNLOAD_CONCURRENCY)

        try:
            async with asyncio.TaskGroup() as task_group:
                for shard_url in shard_urls:
                    task_group.create_task(
                        self._copy_shard(
                            shard_url, snapshot, sizes[shard_url], semaphore, reporter
                        )
                    )
        except ExceptionGroup as eg:
            # Surface the first failure rather than the group
            raise eg.exceptions[0] from eg

        # Only once every shard has landed does the snapshot become readable.
        self._write_success_marker(snapshot)

    async def _copy_shard(
        self,
        shard_url: str,
        snapshot: Snapshot,
        expected: int,
        semaphore: asyncio.Semaphore,
        reporter: Optional[ProgressReporter],
    ) -> None:
        """Copy one upstream shard into its own GCS object."""
        async with semaphore:
            await asyncio.to_thread(
                self._copy_shard_blocking, shard_url, snapshot, expected, reporter
            )

    def _copy_shard_blocking(
        self,
        shard_url: str,
        snapshot: Snapshot,
        expected: int,
        reporter: Optional[ProgressReporter],
    ) -> None:
        """Stream one shard from Wikimedia into GCS. Runs in a worker thread.

        Shards already on GCS at their upstream size are skipped, so a retried run
        resumes rather than re-transferring what landed on the previous attempt.
        """
        filename = shard_url.rsplit("/", 1)[-1]
        blob_name = f"{snapshot.prefix}/{filename}"
        bucket = self.client.bucket(self.gcs_bucket)

        existing = bucket.get_blob(blob_name)
        if existing is not None and expected and existing.size == expected:
            logger.info(
                "Shard already copied, skipping",
                extra={"blob": blob_name, "size": expected},
            )
            self._report_progress(expected, reporter)
            return

        blob = bucket.blob(blob_name, chunk_size=CHUNK_SIZE)
        logger.info(f"Copying shard: gs://{self.gcs_bucket}/{blob_name}")
        try:
            with self.session.get(shard_url, stream=True, timeout=SHARD_TIMEOUT) as resp:  # nosec
                resp.raise_for_status()
                writer: BlobWriter
                with blob.open("wb") as writer:
                    for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
                        self._report_progress(writer.write(chunk), reporter)
        except Exception as e:
            logger.error(f"Unexpected error during GCS streaming for {blob_name}: {e}")
            raise WikipediaFilemanagerError(f"Failed to copy shard {filename}") from e

    def _report_progress(self, written: int, reporter: Optional[ProgressReporter]) -> None:
        """Fold one shard's progress into the run total. Called from worker threads."""
        if reporter is None:
            return
        with self._progress_lock:
            self._copied += written
            reporter.report(self._copied)

    def _write_success_marker(self, snapshot: Snapshot) -> None:
        """Publish the marker that makes a fully copied snapshot readable."""
        self.client.bucket(self.gcs_bucket).blob(
            f"{snapshot.prefix}/{SUCCESS_MARKER}"
        ).upload_from_string(b"")
        logger.info("Published snapshot success marker", extra={"snapshot": snapshot.name})

    def stream_from_gcs(self, snapshot: Snapshot) -> Generator:
        """Streaming reader over every shard of a snapshot, in order.

        Each shard is an independent bzip2 stream, and chaining them here means callers
        still see one continuous sequence of lines.
        """
        shards = self.list_gcs_shards(snapshot)
        if not shards:
            raise WikipediaFilemanagerError(f"No shards found on GCS for {snapshot.name}")

        for blob in shards:
            reader: BlobReader
            with blob.open("rb") as reader:
                with bz2.BZ2File(reader) as stream:
                    yield from stream
