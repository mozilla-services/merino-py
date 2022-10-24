"""Top Pick Navigational Queries Provider"""
import json
import logging
import os
from collections import defaultdict
from typing import Any, Optional

# import httpx
from fastapi import FastAPI
from pydantic import HttpUrl

from merino.config import settings
from merino.providers.base import BaseProvider, BaseSuggestion

SCORE: float = settings.providers.top_pick.score
LOCAL_TOP_PICK_FILE: str = settings.providers.top_pick.top_pick_file_path
QUERY_CHAR_LIMIT: int = settings.providers.top_pick.query_char_limit


logger = logging.getLogger(__name__)


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

    async def query(self, query: str) -> list[BaseSuggestion]:
        """Query Top Pick provider.

        Args:
            - `query`: the query string.
        """
        ...

    def read_domain_list(self, file: str) -> Any:
        """Read local domain list file"""
        if not os.path.exists(LOCAL_TOP_PICK_FILE):
            logger.warning("Local file does not exist")
            raise FileNotFoundError
        try:
            with open(file, "r") as readfile:
                domain_list = json.loads(readfile.read())
                return domain_list
        except Exception as e:
            return e

    def process_suggestion(self, term: str) -> Any:
        """Search for matching domain from search term"""
        pass
