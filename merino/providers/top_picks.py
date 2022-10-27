"""Top Pick Navigational Queries Provider"""
import asyncio
import json
import logging
import os
from collections import defaultdict
from typing import Any, Optional, Union

from fastapi import FastAPI

from merino.config import settings
from merino.providers.base import BaseProvider, BaseSuggestion

SCORE: float = settings.providers.top_picks.score
LOCAL_TOP_PICKS_FILE: str = settings.providers.top_picks.top_picks_file_path
QUERY_CHAR_LIMIT: int = settings.providers.top_picks.query_char_limit


logger = logging.getLogger(__name__)


class Suggestion(BaseSuggestion):
    """Model for Top Pick Query Suggestion"""

    block_id: int
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
    results: list[dict[str, Union[str, list, int]]]
    index_char_range = dict[str, int]

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
            index_results_dict: dict = await asyncio.to_thread(Provider.build_indices)
            self.primary_index: dict = index_results_dict["primary_index"]
            self.secondary_index: list = index_results_dict["secondary_index"]
            self.results: list[Suggestion] = index_results_dict["results"]
            self.index_char_range: dict = index_results_dict["index_char_range"]

        except Exception as e:
            logger.warning(f"Could not instantiate Top Pick Provider: {e}")
            raise e

    def hidden(self) -> bool:  # noqa: D102
        return False

    async def query(self, srequest: str) -> list[BaseSuggestion]:
        """Query Top Pick provider."""
        if srequest.startswith("http"):
            return []
        if ids := self.primary_index.get(srequest, []):
            res = self.results[ids[0]]
            return [res]
        elif ids := self.secondary_index.get(srequest, []):
            res = self.results[ids[0]]
            return [res]
        return []

    @staticmethod
    def read_domain_list(file: str) -> dict[str, Any]:
        """Read local domain list file"""
        if not os.path.exists(file):
            logger.warning("Local file does not exist")
            raise FileNotFoundError
        try:
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
        # A list of suggestions
        results: list[Suggestion] = []
        # A tuple encapsulating the min and max character length in the indexes
        index_char_range: dict[str, int] = {
            "min": QUERY_CHAR_LIMIT,
            "max": QUERY_CHAR_LIMIT,
        }

        for record in domain_list["domains"]:
            index_key: int = len(results)
            domain = record["domain"]

            if len(record["domain"]) < QUERY_CHAR_LIMIT:
                continue

            suggestion = Suggestion(
                block_id=0,
                title=record["title"],
                url=record["url"],
                provider="top_picks",
                is_top_pick=True,
                icon="",
                score=settings.providers.top_picks.score,
            )

            # Insertion of keys into primary index.
            for chars in range(QUERY_CHAR_LIMIT, len(domain) + 1):
                # See configs/default.toml for character limit for Top Picks
                if chars > index_char_range["max"]:
                    index_char_range["max"] = chars
                primary_index[domain[:chars]].append(index_key)

            # Insertion of keys into secondary index.
            for variant in record.get("similars", []):
                for chars in range(QUERY_CHAR_LIMIT, len(variant) + 1):
                    if chars > index_char_range["max"]:
                        index_char_range["max"] = chars
                    secondary_index[variant[:chars]].append(index_key)

            results.append(suggestion)

        return {
            "primary_index": primary_index,
            "secondary_index": secondary_index,
            "results": results,
            "index_char_range": index_char_range,
        }

    @staticmethod
    def build_indices() -> dict[str, Any]:
        """Read domain file, create indices and suggestions"""
        domains = Provider.read_domain_list(LOCAL_TOP_PICKS_FILE)
        index_results_dict = Provider.build_index(domains)
        return index_results_dict