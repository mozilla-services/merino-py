"""A wrapper for Top Picks Provider I/O Interactions"""
import asyncio
import json
import logging
from collections import defaultdict
from datetime import datetime
from enum import Enum
from json import JSONDecodeError
from typing import Any

from google.cloud.storage import Blob, Bucket, Client

from merino.config import settings
from merino.exceptions import BackendError
from merino.providers.top_picks.backends.protocol import TopPicksData

logger = logging.getLogger(__name__)


class DomainDataSource(str, Enum):
    """Source enum for domain data source."""

    REMOTE = "remote"
    LOCAL = "local"


class TopPicksError(BackendError):
    """Error during interaction with Top Picks data."""


class TopPicksLocalFilemanager:
    """Filemanager for processing local Top Picks data."""

    static_file_path: str

    def __init__(self, static_file_path: str) -> None:
        self.static_file_path = static_file_path

    def get_file(self) -> dict[str, Any]:
        """Read local domain list file.

        Raises:
            TopPicksError: If the top picks file path cannot be opened or decoded.
        """
        try:
            with open(self.static_file_path, "r") as readfile:
                domain_list: dict = json.load(readfile)
                return domain_list
        except OSError as os_error:
            raise TopPicksError(
                f"Cannot open file '{self.static_file_path}'"
            ) from os_error
        except JSONDecodeError as json_error:
            raise TopPicksError(
                f"Cannot decode file '{self.static_file_path}'"
            ) from json_error

    @staticmethod
    def _parse_date(file_path: str) -> datetime | None:
        """Parse the datetime from the file name."""
        try:
            return datetime.fromtimestamp(int(file_path.split("_")[0]))
        except (AttributeError, TypeError, ValueError) as e:
            logger.error(f"Cannot parse date from local file {file_path}: {e}")
            return None


class TopPicksRemoteFilemanager:
    """Filemanager for processing local Top Picks data."""

    client: Client
    gcs_project_path: str
    gcs_bucket_path: str

    def __init__(
        self,
        gcs_project_path: str,
        gcs_bucket_path: str,
    ) -> None:
        self.gcs_project_path = gcs_project_path
        self.gcs_bucket_path = gcs_bucket_path

    def create_gcs_client(self) -> Client:
        """Initialize the GCS Client connection."""
        return Client(self.gcs_project_path)

    @staticmethod
    def _parse_date(blob: Blob) -> datetime | None:
        """Parse the datetime metadata from the file."""
        try:
            generation_timestamp: int = blob.generation
            # Returned value stored on GCS metadata in microseconds.
            return datetime.fromtimestamp(int(generation_timestamp / 10_000_000))
        except (AttributeError, TypeError, ValueError) as e:
            logger.error(
                f"Cannot parse date, generation attribute not found for {blob}: {e}"
            )
            return None

    def get_file(self, client: Client) -> tuple[dict[str, Any], int]:
        """Read remote domain list file.

        Raises:
            TopPicksError: If the top picks file cannot be accessed.
        Returns:
            Dictionary containing domain list
        """
        try:
            bucket: Bucket = client.get_bucket(self.gcs_bucket_path)
            blob: Blob = bucket.get_blob("top_picks_latest.json")
            blob_generation = blob.generation
            blob_data = blob.download_as_text()
            blob_date: datetime | None = self._parse_date(blob=blob)
            current_date: datetime = datetime.now()
            file_contents: dict = json.loads(blob_data)
            logger.info(
                f"Domain file {blob.name} acquired. File generated on: {blob_date}."
                f"Updated in Merino backend on {current_date}."
            )
            return (file_contents, blob_generation)
        except Exception as e:
            raise TopPicksError(f"Error getting remote file {e}")


class TopPicksBackend:
    """Backend that indexes and provides Top Pick data."""

    def __init__(
        self,
        top_picks_file_path: str | None,
        query_char_limit: int,
        firefox_char_limit: int,
        domain_blocklist: set[str],
    ) -> None:
        """Initialize Top Picks backend.

        Raises:
            ValueError: If the top picks file path is not specified.
        """
        if not top_picks_file_path:
            raise ValueError("Top Picks domain file not specified.")

        self.top_picks_file_path = top_picks_file_path
        self.query_char_limit = query_char_limit
        self.firefox_char_limit = firefox_char_limit
        self.domain_blocklist = {entry.lower() for entry in domain_blocklist}
        self._generation: int | None = None

    async def fetch(self) -> TopPicksData:
        """Fetch Top Picks suggestions from domain list.

        Raises:
            TopPicksError: If the top picks file path is not specified.
        """
        return await asyncio.to_thread(self.build_indices)

    @staticmethod
    def read_domain_list(file: str) -> dict[str, Any]:
        """Read local domain list file.

        Raises:
            TopPicksError: If the top picks file path cannot be opened or decoded.
        """
        try:
            with open(file, "r") as readfile:
                domain_list: dict = json.load(readfile)
                return domain_list
        except OSError as os_error:
            raise TopPicksError(f"Cannot open file '{file}'") from os_error
        except JSONDecodeError as json_error:
            raise TopPicksError(f"Cannot decode file '{file}'") from json_error

    def build_index(self, domain_list: dict[str, Any]) -> TopPicksData:
        """Construct indexes and results from Top Picks"""
        # A dictionary of keyed values that point to the matching index
        primary_index: defaultdict = defaultdict(list)
        # A dictionary of keyed values that point to the matching index
        secondary_index: defaultdict = defaultdict(list)
        # A dictionary encapsulating short domains and their similars
        short_domain_index: defaultdict = defaultdict(list)
        # A list of suggestions
        results: list[dict] = []

        # These variables hold the max and min lengths of queries possible given the domain list.
        # See configs/default.toml for character limit for Top Picks
        # For testing, see configs/testing.toml for character limit for Top Picks
        query_min: int = self.query_char_limit
        query_max: int = self.query_char_limit

        for record in domain_list["domains"]:
            index_key: int = len(results)
            domain: str = record["domain"].strip().lower()

            if domain in self.domain_blocklist:
                continue

            if len(domain) > query_max:
                query_max = len(domain)

            suggestion: dict = {
                "block_id": 0,
                "title": record["title"],
                "url": record["url"],
                "provider": "top_picks",
                "is_top_pick": True,
                "is_sponsored": False,
                "icon": record["icon"],
            }

            # Insertion of short keys between Firefox limit of 2 and self.query_char_limit - 1
            # For similars equal to or longer than self.query_char_limit, the values are added
            # to the secondary index.
            if self.firefox_char_limit <= len(domain) <= (self.query_char_limit - 1):
                for chars in range(self.firefox_char_limit, len(domain) + 1):
                    short_domain_index[domain[:chars]].append(index_key)
                for variant in record.get("similars", []):
                    if len(variant) >= self.query_char_limit:
                        # Long variants will be indexed later into `secondary_index`
                        continue

                    for chars in range(self.firefox_char_limit, len(variant) + 1):
                        short_domain_index[variant[:chars]].append(index_key)

            # Insertion of keys into primary index.
            for chars in range(self.query_char_limit, len(domain) + 1):
                primary_index[domain[:chars]].append(index_key)

            # Insertion of keys into secondary index.
            for variant in record.get("similars", []):
                if len(variant) > query_max:
                    query_max = len(variant)
                for chars in range(self.query_char_limit, len(variant) + 1):
                    secondary_index[variant[:chars]].append(index_key)

            results.append(suggestion)

        return TopPicksData(
            primary_index=primary_index,
            secondary_index=secondary_index,
            short_domain_index=short_domain_index,
            results=results,
            query_min=query_min,
            query_max=query_max,
            query_char_limit=self.query_char_limit,
            firefox_char_limit=self.firefox_char_limit,
        )

    def build_indices(self) -> TopPicksData:
        """Read domain file, create indices and suggestions"""
        domain_data_source: str = settings.providers.top_picks.domain_data_source

        match domain_data_source:
            case DomainDataSource.REMOTE:
                remote_filemanager = TopPicksRemoteFilemanager(
                    gcs_project_path=settings.providers.top_picks.gcs_project,
                    gcs_bucket_path=settings.providers.top_picks.gcs_bucket,
                )
                client: Client = remote_filemanager.create_gcs_client()
                remote_domains, remote_generation = remote_filemanager.get_file(client)
                self._generation = remote_generation
                remote_index_results: TopPicksData = self.build_index(remote_domains)
                logger.info(
                    f"Top Picks Domain Data loaded remotely from GCS.\
                    {self._generation}"
                )

                return remote_index_results
            case DomainDataSource.LOCAL:
                local_filemanager = TopPicksLocalFilemanager(
                    static_file_path=settings.providers.top_picks.top_picks_file_path
                )
                local_domains = local_filemanager.get_file()
                local_index_results: TopPicksData = self.build_index(local_domains)
                logger.info("Top Picks Domain Data loaded locally from static file.")
                return local_index_results
            case _:
                logger.error("Could not generate index from local or remote source.")
                raise TopPicksError(
                    "Could not generate index from local or remote source."
                )
