"""Top Pick Navigational Queries Provider"""
import asyncio
import json
import logging
import os
from collections import defaultdict
from enum import Enum
from typing import Any, Final, Optional

# import httpx
from fastapi import FastAPI
from pydantic import HttpUrl

from merino.config import settings
from merino.providers.base import BaseProvider, BaseSuggestion

SCORE: float = settings.providers.top_pick.score
LOCAL_TOP_PICK_FILE: str = settings.providers.top_pick.top_pick_file_path
QUERY_CHAR_LIMIT: int = settings.providers.top_pick.query_char_limit
# Used whenever the `icon` field is missing from the top pick payload.
MISSING_ICON_ID: Final = "-1"


logger = logging.getLogger(__name__)


class TopPickCategory(str, Enum):
    """Enum for Top Pick Category.

    There are two possible Top Pick suggestions.
    A Primary suggestion means the query term matched the string exactly.
    A Secondary suggestion captures a mis-typed or similar query to the match.
    """

    PRIMARY: Final = "PRIMARY"
    SECONDARY: Final = "SECONDARY"


class Suggestion(BaseSuggestion):
    """Model for Top Pick Query Suggestion"""

    block_id: int
    icon: Optional[HttpUrl]
    full_keyword: str
    domain: str
    rank: int
    title: str
    url: HttpUrl
    is_sponsored: bool
    is_top_pick: bool
    score: float
    impression_url: HttpUrl
    click_url: HttpUrl


class Provider(BaseProvider):
    """Top Pick Query Suggestion Provider"""

    # In normal usage this is None, but tests can create the provider with a
    # FastAPI instance to fetch mock responses from it. See `__init__()`.
    _app: Optional[FastAPI]

    domain_list: dict[str, Any] = {}
    suggestions: dict[str, int] = {}
    primary_index: defaultdict = defaultdict(list)
    primary_results: list[dict[str, Any]] = []
    secondary_index: defaultdict = defaultdict(list)
    secondary_results: list[dict[str, Any]] = []
    icons: dict[int, str] = {}

    def __init__(
        self,
        app: Optional[FastAPI] = None,
        name: str = "top_pick",
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
            primary, secondary = await asyncio.to_thread(Provider.build_indices())
            self.primary_index = primary[0]
            self.primary_results = primary[1]
            self.secondary_index = secondary[0]
            self.secondary_results = secondary[1]
        except Exception as e:
            logger.warning(f"Could not instantiate Top Pick Provider: {e}")

    def hidden(self) -> bool:  # noqa: D102
        return False

    async def query(self, q: str) -> Optional[list[BaseSuggestion]]:  # type: ignore
        """Query Top Pick provider.

        Args:
            - `q`: the query string.
        """
        if len(q) < QUERY_CHAR_LIMIT:
            return []
        if (id := self.primary_index.get(q)) is not None:
            res = self.primary_results[id]
            suggestion_dict = {
                "block_id": res.get("rank"),
                "rank": res.get("rank"),
                "full_keyword": q,
                "title": res.get("title"),
                "domain": res.get("domain"),
                "url": res.get("url"),
                "impression_url": res.get("url"),
                "click_url": res.get("url"),
                "provider": self.name,
                "is_top_pick": True,
                "is_sponsored": False,
                "icon": res.get(int(res.get("icon", MISSING_ICON_ID))),
                "score": SCORE,
            }
            Suggestion(**suggestion_dict)
        elif (id := self.secondary_index.get(q)) is not None:
            res = self.secondary_results[id]
        else:
            res = None
        return []

    @staticmethod
    def read_domain_list(file: str) -> Any:
        """Read local domain list file"""
        if not os.path.exists(file):
            logger.warning("Local file does not exist")
            raise FileNotFoundError
        try:
            with open(file, "r") as readfile:
                domain_list: dict[str, Any] = json.load(readfile)
                return domain_list
        except Exception as e:
            logger.warning("Cannot Process File: {e}")
            return e

    @staticmethod
    def build_index(domain_list: dict[str, Any]) -> Any:
        """Construct indexes and results from Top Picks"""
        domains: list[dict[str, Any]] = domain_list["domains"]["items"]
        index: defaultdict = defaultdict(list)
        results: list[dict[str, Any]] = []

        for domain in domains:
            index_key = len(results)
            for chars in range(QUERY_CHAR_LIMIT, len(domain) + 1):
                # See configs/default.toml for character limit for Top Picks
                index[domain["domain"][:chars]].append(index_key)
            results.append(domain)

        alt_domains: list[dict[str, Any]] = []
        secondary_index: defaultdict = defaultdict(list)
        secondary_results: list[dict[str, Any]] = []

        for domain in domains:
            if not domain["similars"]:
                alt_domains.append(domain)
            else:
                for alt in domain["similars"]:
                    alt_domain = domain.copy()
                    alt_domain.update({"term": alt})
                    alt_domains.append(alt_domain)

        for domain in alt_domains:
            index_key = len(secondary_results)
            for chars in range(QUERY_CHAR_LIMIT, len(domain) + 1):
                # See configs/default.toml for character limit for Top Picks
                secondary_index[domain["term"][:chars]].append(index_key)
            secondary_results.append(domain)
        return (index, results), (secondary_index, secondary_results)

    @staticmethod
    def build_indices() -> Any:
        """Read domain file, create indexes and suggestions"""
        domains = Provider.read_domain_list(LOCAL_TOP_PICK_FILE)
        primary, secondary = Provider.build_index(domains)
        return primary, secondary


# {'exxa': [0], 'exxam': [0], 'exxamp': [0], 'exxampl': [0],
# 'exam': [1], 'examp': [1], 'exampp': [1], 'examppl': [1],
# 'eexa': [2], 'eexam': [2], 'eexamp': [2], 'eexampl': [2],
# 'fire': [3, 6, 7], 'firef': [3, 7], 'firefo': [3, 7],
# 'firefox': [3, 7], 'foye': [4], 'foyer': [4],
# 'foyerf': [4], 'foyerfo': [4], 'fiir': [5],
# 'fiire': [5], 'fiiref': [5], 'fiirefo': [5],
# 'fires': [6], 'firesf': [6], 'firesfo': [6],
# 'mozz': [8], 'mozzi': [8], 'mozzil': [8],
# 'mozzill': [8], 'mozi': [9], 'mozil': [9],
# 'mozila': [9, 9]})
