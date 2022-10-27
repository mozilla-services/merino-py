"""Top Pick Navigational Queries Provider"""
import asyncio
import json
import logging
import os
from collections import defaultdict
from typing import Any, Final, Optional

from fastapi import FastAPI

from merino.config import settings
from merino.providers.base import BaseProvider, BaseSuggestion

SCORE: float = settings.providers.top_picks.score
LOCAL_TOP_PICKS_FILE: str = settings.providers.top_picks.top_picks_file_path
QUERY_CHAR_LIMIT: int = settings.providers.top_picks.query_char_limit
# Used whenever the `icon` field is missing from the top pick payload.
MISSING_ICON_ID: Final = "-1"


logger = logging.getLogger(__name__)


class Suggestion(BaseSuggestion):
    """Model for Top Pick Query Suggestion"""

    block_id: int
    domain: str
    rank: int
    is_top_pick: bool
    score: float
    is_sponsored: bool = False


class Provider(BaseProvider):
    """Top Pick Query Suggestion Provider"""

    # In normal usage this is None, but tests can create the provider with a
    # FastAPI instance to fetch mock responses from it. See `__init__()`.
    _app: Optional[FastAPI]

    primary_index: defaultdict = defaultdict(list)
    secondary_index: defaultdict = defaultdict(list)
    results: list[dict[str, Any]] = []

    def __init__(
        self,
        app: Optional[FastAPI] = None,
        name: str = "top_picks",
        enabled_by_default: bool = False,
        **kwargs: Any,
    ) -> None:
        self._app = app
        self._name = name
        self._enabled_by_default = enabled_by_default
        super().__init__(**kwargs)

    async def initialize(self) -> None:
        """Initialize the provider."""
        try:
            index_results_dict: dict = await asyncio.to_thread(Provider.build_indices)
            self.primary_index = index_results_dict["primary_index"]
            self.secondary_index = index_results_dict["secondary_index"]
            self.results = index_results_dict["results"]

        except Exception as e:
            logger.warning(f"Could not instantiate Top Pick Provider: {e}")
            raise e

    def hidden(self) -> bool:  # noqa: D102
        return False

    async def query(self, q: str) -> Any:
        """Query Top Pick provider."""
        if q.startswith("http"):
            return []
        if len(q) < QUERY_CHAR_LIMIT:
            return []
        if ids := self.primary_index.get(q, []):
            res = self.results[ids[0]]
            logger.warning(res)
            return Suggestion(**res)
        elif ids := self.secondary_index.get(q, []):
            res = self.results[ids[0]]
            return Suggestion(**res)
        return []

    @staticmethod
    def read_domain_list(file: str) -> Any:
        """Read local domain list file"""
        if not os.path.exists(file):
            logger.warning("Local file does not exist")
            raise FileNotFoundError
        try:
            with open(file, "r") as readfile:
                domain_list = json.load(readfile)
                return domain_list
        except Exception as e:
            logger.warning("Cannot Process File: {e}")
            raise e

    @staticmethod
    def build_index(domain_list: Any) -> Any:
        """Construct indexes and results from Top Picks"""
        primary_index: defaultdict = defaultdict(list)
        secondary_index: defaultdict = defaultdict(list)
        results: list[dict[str, Any]] = []

        for record in domain_list["domains"]:
            index_key = len(results)

            if len(record["domain"]) < QUERY_CHAR_LIMIT:
                continue

            suggestion = {
                "block_id": 0,
                "rank": record["rank"],
                "title": record["title"],
                "domain": record["domain"],
                "url": record["url"],
                "provider": "top_picks",
                "is_top_pick": True,
                "icon": "",
                "score": settings.providers.top_picks.score,
            }

            # Insertion of keys into primary index.
            for chars in range(QUERY_CHAR_LIMIT, len(record["domain"]) + 1):
                # See configs/default.toml for character limit for Top Picks
                primary_index[record["domain"][:chars]].append(index_key)

            # Insertion of keys into primary index.
            for variant in record.get("similars", []):
                for chars in range(QUERY_CHAR_LIMIT, len(variant) + 1):
                    secondary_index[variant[:chars]].append(index_key)

            results.append(suggestion)

        return {
            "primary_index": primary_index,
            "secondary_index": secondary_index,
            "results": results,
        }

    @staticmethod
    def build_indices() -> Any:
        """Read domain file, create indices and suggestions"""
        domains = Provider.read_domain_list(LOCAL_TOP_PICKS_FILE)
        index_results_dict = Provider.build_index(domains)
        return index_results_dict
