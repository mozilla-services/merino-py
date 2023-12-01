"""A wrapper for Top Picks Provider I/O Interactions"""
import asyncio
import json
import logging
from collections import defaultdict
from json import JSONDecodeError
from typing import Any

from merino.config import settings
from merino.exceptions import BackendError
from merino.providers.top_picks.backends.filemanager import (
    DomainDataSource,
    TopPicksLocalFilemanager,
    TopPicksRemoteFilemanager,
)
from merino.providers.top_picks.backends.protocol import TopPicksData

logger = logging.getLogger(__name__)


class TopPicksError(BackendError):
    """Error during interaction with Top Picks data."""


class TopPicksBackend:
    """Backend that indexes and provides Top Pick data."""

    generation: int

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
        self.generation: int = 0

    async def fetch(self) -> TopPicksData | None:
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
            logger.error(f"Error opening local domain file: {os_error}")
            raise TopPicksError(f"Cannot open file '{file}'") from os_error
        except JSONDecodeError as json_error:
            logger.error(f"Error decoding local domain file: {json_error}")
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

    def build_indices(self) -> TopPicksData | None:
        """Read domain file, create indices and suggestions"""
        domain_data_source: str = settings.providers.top_picks.domain_data_source

        match domain_data_source:
            case DomainDataSource.REMOTE:
                remote_filemanager = TopPicksRemoteFilemanager(
                    gcs_project_path=settings.providers.top_picks.gcs_project,
                    gcs_bucket_path=settings.providers.top_picks.gcs_bucket,
                )
                client = remote_filemanager.create_gcs_client()
                if (remote_file := remote_filemanager.get_file(client)) is not None:
                    remote_domains, remote_generation = remote_file
                    self.generation = remote_generation
                    remote_index_results: TopPicksData = self.build_index(
                        remote_domains
                    )
                    logger.info("Top Picks Domain Data loaded remotely from GCS.")
                    return remote_index_results
                return None
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
