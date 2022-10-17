"""Top Pick Navigational Queries Provider"""
import logging
import os
from typing import Any, Optional

# import httpx
from fastapi import FastAPI
from pydantic import HttpUrl

from merino.config import settings
from merino.providers.base import BaseProvider, BaseSuggestion

SCORE: float = settings.providers.top_pick.score
LOCAL_TOP_PICK_FILE: str = settings.providers.top_pick.top_pick_file_path
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
    results: list[dict[str, Any]] = []
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
        self._is_top_pick = True
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
            raise Exception
        try:
            with open(file, "r") as readfile:
                domain_list = readfile.readlines()
                return domain_list
        except Exception as e:
            return e
