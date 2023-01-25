"""Manage files between wikimedia exports and gcs bucket"""
import logging
import re
from datetime import datetime as dt
from gzip import GzipFile
from html.parser import HTMLParser
from typing import Generator, List, Optional, Pattern, Tuple
from urllib.parse import urljoin

import requests
from google.cloud.storage import Blob, Client
from google.cloud.storage.fileio import BlobReader, BlobWriter

logger = logging.getLogger(__name__)


class DirectoryParser(HTMLParser):
    """Parse the directory listing to find the specified file."""

    filter: Pattern[str]
    file_paths: List[str] = []

    def __init__(self, filter_wildcard: Pattern[str]) -> None:
        super().__init__()
        self.filter = re.compile(filter_wildcard)

    def _is_href(self, k: str, v: str) -> bool:
        return k == "href" and re.search(self.filter, v) is not None

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        """When the parser encounters a start tag check for Anchor and push into list."""
        if tag.lower() == "a":
            hrefs = [(k, v) for k, v in attrs if v is not None and self._is_href(k, v)]
            self.file_paths.extend([v for _, v in hrefs])


class FileManager:
    """Tools for managing files on wikimedia export directory and copying into GCS"""

    base_url: Optional[str]
    gcs_bucket: str
    object_prefix: str
    file_pattern: Pattern
    client: Client

    def __init__(
        self, gcs_bucket: str, gcs_project: str, export_base_url: Optional[str] = None
    ) -> None:
        self.file_pattern = re.compile("^enwiki-(\\d+)-cirrussearch-content.json.gz")
        self.client = Client(gcs_project)
        self.base_url = export_base_url
        if "/" in gcs_bucket:
            self.gcs_bucket, self.object_prefix = gcs_bucket.split("/", 1)
        else:
            self.gcs_bucket = gcs_bucket
            self.object_prefix = ""

    def get_latest_dump(self, latest_gcs: Blob) -> str | None:
        """Find the latest export that's older than the latest on gcs."""
        if self.base_url is None:
            raise RuntimeError("Invalid base_url")
        resp = requests.get(self.base_url)
        parser = DirectoryParser(self.file_pattern)
        parser.feed(str(resp.content))
        links = parser.file_paths
        if len(links) == 1:
            name = links[0]
            url = urljoin(self.base_url, name)
            last_gcs_date = self._parse_date(str(latest_gcs.name))
            link_date = self._parse_date(name)
            if last_gcs_date < link_date:
                return url
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
        """Find the most recent file on GCS"""
        bucket = self.client.bucket(self.gcs_bucket)
        blobs: List[Blob] = [b for b in bucket.list_blobs(prefix=self.object_prefix)]
        blobs.sort(key=lambda b: self._parse_date(str(b.name)))
        return blobs[-1]

    def stream_latest_dump_to_gcs(self, latest_gcs: Optional[Blob] = None) -> Blob:
        """Stream the latest wikimedia dump to GCS"""
        if not latest_gcs:
            latest_gcs = self.get_latest_gcs()
        latest_dump_url = self.get_latest_dump(latest_gcs)
        logger.info("latest_dump_url", extra={"ldurl": latest_dump_url})
        if latest_dump_url:
            self._stream_dump_to_gcs(latest_dump_url)
        else:
            logger.info("Currently up to date")

        return latest_gcs

    def stream_latest_from_gcs(self) -> Generator:
        """Stream latest file from GCS"""
        for chunk in self._stream_from_gcs(self.get_latest_gcs()):
            yield chunk

    def _stream_dump_to_gcs(self, dump_url: str):
        """Write latest to GCS without storing locally"""
        name = "{}/{}".format(self.object_prefix, dump_url.split("/")[-1])
        blob = self.client.bucket(self.gcs_bucket).blob(name)
        with requests.get(dump_url, stream=True) as resp:
            content_len = int(resp.headers.get("Content-Length", 0))
            resp.raise_for_status()
            logger.info("Writing to GCS: gs://{}/{}".format(self.gcs_bucket, blob.name))
            logger.info("Total File Size: {}".format(content_len))
            writer: BlobWriter
            with blob.open("wb") as writer:
                for chunk in resp.iter_content(chunk_size=8129):
                    writer.write(chunk)
                    perc_done = round(len(chunk) / content_len * 100, 5)
                    if perc_done > 1 and perc_done % 2 == 0:
                        logger.info(
                            "Download progress: {}%".format(perc_done),
                            extra={
                                "url": dump_url,
                                "destination": blob.name,
                                "percent_complete": perc_done,
                                "total_size": content_len,
                            },
                        )

    def _stream_from_gcs(self, blob: Blob) -> Generator:
        """Streaming reader from GCS"""
        reader: BlobReader
        with blob.open("rb") as reader:
            with GzipFile(fileobj=reader) as gz:
                for line in gz:
                    yield line
