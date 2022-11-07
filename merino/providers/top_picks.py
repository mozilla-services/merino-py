"""Top Pick Navigational Queries Provider"""
import asyncio
import json
import logging
import os
from collections import defaultdict
from typing import Any, Final, Optional

from fastapi import FastAPI

from merino.config import settings
from merino.providers.base import BaseProvider, BaseSuggestion, SuggestionRequest

SCORE: float = settings.providers.top_picks.score
LOCAL_TOP_PICKS_FILE: str = settings.providers.top_picks.top_picks_file_path
QUERY_CHAR_LIMIT: int = settings.providers.top_picks.query_char_limit
FIREFOX_CHAR_LIMIT: Final = 2


logger = logging.getLogger(__name__)


class Suggestion(BaseSuggestion):
    """Model for Top Pick Query Suggestion"""

    block_id: int
    is_top_pick: bool


class Provider(BaseProvider):
    """Top Pick Query Suggestion Provider"""

    # In normal usage this is None, but tests can create the provider with a
    # FastAPI instance to fetch mock responses from it. See `__init__()`.
    _app: Optional[FastAPI]

    primary_index: defaultdict = defaultdict(list)
    secondary_index: defaultdict = defaultdict(list)
    short_domain_index: defaultdict = defaultdict(list)
    results: list[Suggestion]
    query_min: int
    query_max: int

    def __init__(
        self,
        app: Optional[FastAPI] = None,
        name: str = "top_picks",
        enabled_by_default: bool = False,
    ) -> None:
        self._app = app
        self._name = name
        self._enabled_by_default = enabled_by_default

    async def initialize(self) -> None:
        """Initialize the provider."""
        try:
            index_results: dict[str, Any] = await asyncio.to_thread(
                Provider.build_indices
            )
            self.primary_index: defaultdict = index_results["primary_index"]
            self.secondary_index: defaultdict = index_results["secondary_index"]
            self.short_domain_index: defaultdict = index_results["short_domain_index"]
            self.results: list[Suggestion] = index_results["results"]
            self.query_min: int = index_results["index_char_range"][0]
            self.query_max: int = index_results["index_char_range"][1]

        except Exception as e:
            logger.warning(f"Could not instantiate Top Pick Provider: {e}")
            raise e

    def hidden(self) -> bool:  # noqa: D102
        return False

    async def query(self, srequest: SuggestionRequest) -> list[BaseSuggestion]:
        """Query Top Pick provider and return suggestion"""
        # Ignore https:// and http://
        if srequest.query.startswith("http"):
            return []
        # Suggestions between Firefox char min of 2 and query limit - 1 for short domains
        if len(srequest.query) >= FIREFOX_CHAR_LIMIT and len(srequest.query) <= (
            QUERY_CHAR_LIMIT - 1
        ):
            if ids := self.short_domain_index.get(srequest.query):
                res = self.results[ids[0]]
                return [res]
        # Ignore requests below or above character minimums
        if len(srequest.query) < self.query_min or len(srequest.query) > self.query_max:
            return []
        if ids := self.primary_index.get(srequest.query):
            res = self.results[ids[0]]
            return [res]
        elif ids := self.secondary_index.get(srequest.query):
            res = self.results[ids[0]]
            return [res]
        return []

    @staticmethod
    def read_domain_list(file: str) -> dict[str, Any]:
        """Read local domain list file"""
        try:
            if not os.path.exists(file):
                logger.warning("Local file does not exist")
                raise FileNotFoundError
            with open(file, "r") as readfile:
                domain_list: dict = json.load(readfile)
                return domain_list
        except Exception as e:
            logger.warning("Cannot Process File: {e}")
            raise e

    @staticmethod
    def build_index(domain_list: dict[str, Any]) -> dict[str, Any]:
        """Construct indexes and results from Top Picks"""
        # A dictionary of keyed values that point to the matching index
        primary_index: defaultdict = defaultdict(list)
        # A dictionary of keyed values that point to the matching index
        secondary_index: defaultdict = defaultdict(list)
        # A dictionary encapsulating short domains
        short_domain_index: defaultdict = defaultdict(list)
        # A list of suggestions
        results: list[Suggestion] = []

        # These variables hold the max and min lengths
        # of queries possible given the domain list.
        # See configs/default.toml for character limit for Top Picks
        # For testing, see configs/testing.toml for character limit for Top Picks
        query_min: int = QUERY_CHAR_LIMIT
        query_max: int = QUERY_CHAR_LIMIT

        for record in domain_list["domains"]:
            index_key: int = len(results)
            domain = record["domain"]

            if len(domain) > query_max:
                query_max = len(domain)

            suggestion = Suggestion(
                block_id=0,
                title=record["title"],
                url=record["url"],
                provider="top_picks",
                is_top_pick=True,
                is_sponsored=False,
                icon=record["icon"],
                score=SCORE,
            )

            # Insertion of short keys between Firefox limit of 2 and QUERY_CHAR_LIMIT - 1
            if (
                len(domain) >= FIREFOX_CHAR_LIMIT
                and len(domain) <= QUERY_CHAR_LIMIT - 1
            ):
                for chars in range(FIREFOX_CHAR_LIMIT, len(domain) + 1):
                    short_domain_index[domain[:chars]].append(index_key)
                for variant in record.get("similars", []):
                    for chars in range(FIREFOX_CHAR_LIMIT, len(variant) + 1):
                        short_domain_index[variant[:chars]].append(index_key)

            # Insertion of keys into primary index.
            for chars in range(QUERY_CHAR_LIMIT, len(domain) + 1):
                primary_index[domain[:chars]].append(index_key)

            # Insertion of keys into secondary index.
            for variant in record.get("similars", []):
                if len(variant) > query_max:
                    query_max = len(variant)
                for chars in range(QUERY_CHAR_LIMIT, len(variant) + 1):
                    secondary_index[variant[:chars]].append(index_key)

            results.append(suggestion)

        return {
            "primary_index": primary_index,
            "secondary_index": secondary_index,
            "short_domain_index": short_domain_index,
            "results": results,
            "index_char_range": (query_min, query_max),
        }

    @staticmethod
    def build_indices() -> dict[str, Any]:
        """Read domain file, create indices and suggestions"""
        domains = Provider.read_domain_list(LOCAL_TOP_PICKS_FILE)
        index_results = Provider.build_index(domains)
        return index_results
