"""Top Pick Navigational Queries Provider"""
import json
import logging
import os

# from asyncio import to_thread
from collections import defaultdict
from enum import Enum
from typing import Any, Final, Optional, Union

# import httpx
from fastapi import FastAPI
from pydantic import HttpUrl

from merino.config import settings
from merino.providers.base import BaseProvider, BaseSuggestion

SCORE: float = settings.providers.top_pick.score
LOCAL_TOP_PICK_FILE: str = settings.providers.top_pick.top_pick_file_path
QUERY_CHAR_LIMIT: int = settings.providers.top_pick.query_char_limit


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
    icon: Optional[HttpUrl] = None
    full_keyword: str
    title: str
    is_sponsored_suggestion: bool
    top_pick: bool
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
    # Store the value to avoid fetching it from settings every time as that'd
    # require a three-way dict lookup.
    titles: list[dict[str, Any]] = []
    score: float = settings.providers.adm.score
    last_fetch_at: float

    def __init__(
        self,
        app: Optional[FastAPI] = None,
        name: str = "top_pick",
        enabled_by_default: bool = False,
        **kwargs: Any
    ) -> None:
        self._app = app
        self._name = name
        self._enabled_by_default = enabled_by_default
        super().__init__(**kwargs)

    async def initialize(self) -> None:
        """Initialize the provider."""
        ...

    def hidden(self) -> bool:  # noqa: D102
        return False

    async def query(self, q: str) -> Optional[list[BaseSuggestion]]:  # type: ignore
        """Query Top Pick provider.

        Args:
            - `q`: the query string.
        """
        if len(q) < QUERY_CHAR_LIMIT:
            return []
        match q:
            case _:
                logger.warning("Unexpected Top Pick response")
        return []

    @staticmethod
    def read_domain_list(file: str) -> Union[dict[str, Any], Exception]:
        """Read local domain list file"""
        if not os.path.exists(LOCAL_TOP_PICK_FILE):
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
    def build_index(domain_list: dict[str, Any], category: TopPickCategory) -> None:
        """Construct indexes and results from Top Picks"""
        _index: defaultdict = defaultdict(int)
        _results: list[dict[str, Any]] = []

        domains = domain_list["domains"]["items"]
        if category == TopPickCategory.PRIMARY:
            for domain in domains:
                index_key = len(_results)
                for chars in range(QUERY_CHAR_LIMIT, len(domain) + 1):
                    # See configs/default.toml for character limit for Top Picks
                    _index[domain["domain"][:chars]] = index_key
                _results.append(domain)
        elif category == TopPickCategory.SECONDARY:
            for domain in domains:
                index_key = len(_results)
                similars = domain["similars"]
                for similar in similars:
                    for chars in range(QUERY_CHAR_LIMIT, len(similar) + 1):
                        # See configs/default.toml for character limit for Top Picks
                        _index[domain["domain"][:chars]] = index_key
                    _results.append(domain)
