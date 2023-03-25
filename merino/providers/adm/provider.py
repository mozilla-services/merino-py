"""AdM integration that uses the remote-settings provided data."""
import asyncio
import logging
import time
from enum import Enum, unique
from typing import Any, Final, Optional

from pydantic import HttpUrl

from merino import cron
from merino.providers.adm.backends.protocol import AdmBackend, SuggestionContent
from merino.providers.base import BaseProvider, BaseSuggestion, SuggestionRequest

logger = logging.getLogger(__name__)


@unique
class IABCategory(str, Enum):
    """Enum for IAB categories.

    Suggestions with the category `SHOPPING` will be labelled as
    sponsored suggestions. Otherwise, they're nonsponsored.
    """

    SHOPPING: Final = "22 - Shopping"
    EDUCATION: Final = "5 - Education"


# Used whenever the `icon` field is missing from the suggestion payload.
MISSING_ICON_ID: Final = "-1"


class SponsoredSuggestion(BaseSuggestion):
    """Model for sponsored suggestions."""

    block_id: int
    full_keyword: str
    advertiser: str
    impression_url: HttpUrl
    click_url: HttpUrl


class NonsponsoredSuggestion(BaseSuggestion):
    """Model for nonsponsored suggestions.

    Both `impression_url` and `click_url` are optional compared to
    sponsored suggestions.
    """

    block_id: int
    full_keyword: str
    advertiser: str
    impression_url: Optional[HttpUrl] = None
    click_url: Optional[HttpUrl] = None


class Provider(BaseProvider):
    """Suggestion provider for adMarketplace through Remote Settings."""

    suggestion_content: SuggestionContent
    # Store the value to avoid fetching it from settings every time as that'd
    # require a three-way dict lookup.
    score: float
    score_wikipedia: float
    last_fetch_at: float
    cron_task: asyncio.Task
    backend: AdmBackend
    resync_interval_sec: float

    def __init__(
        self,
        backend: AdmBackend,
        score: float,
        score_wikipedia: float,
        name: str,
        resync_interval_sec: float,
        enabled_by_default: bool = True,
        **kwargs: Any,
    ) -> None:
        """Store the given Remote Settings backend on the provider."""
        self.backend = backend
        self.score = score
        self.score_wikipedia = score_wikipedia
        self.resync_interval_sec = resync_interval_sec
        self.suggestion_content = SuggestionContent(
            suggestions={}, full_keywords=[], results=[], icons={}
        )
        self._name = name
        self._enabled_by_default = enabled_by_default
        super().__init__(**kwargs)

    async def initialize(self) -> None:
        """Initialize cron job."""
        try:
            await self._fetch()
        except Exception as e:
            logger.warning(
                "Failed to fetch data from Remote Settings, will retry it soon",
                extra={"error message": f"{e}"},
            )
            # Set the last fetch timestamp to 0 so that the cron job will retry
            # the fetch upon the next tick.
            self.last_fetch_at = 0

        # Run a cron job that resyncs data from Remote Settings in the background.
        cron_job = cron.Job(
            name="resync_rs_data",
            interval=self.resync_interval_sec,
            condition=self._should_fetch,
            task=self._fetch,
        )
        # Store the created task on the instance variable. Otherwise it will get
        # garbage collected because asyncio's runtime only holds a weak
        # reference to it.
        self.cron_task = asyncio.create_task(cron_job())

    def _should_fetch(self) -> bool:
        """Check if it should fetch data from Remote Settings."""
        return (time.time() - self.last_fetch_at) >= self.resync_interval_sec

    async def _fetch(self) -> None:
        """Fetch suggestions, keywords, and icons from Remote Settings."""
        self.suggestion_content = await self.backend.fetch()
        self.last_fetch_at = time.time()

    def hidden(self) -> bool:  # noqa: D102
        return False

    def normalize_query(self, query: str) -> str:
        """Convert a query string to lowercase and remove trailing spaces."""
        return query.strip().lower()

    async def query(self, srequest: SuggestionRequest) -> list[BaseSuggestion]:
        """Provide suggestion for a given query."""
        q: str = srequest.query
        if (suggest_look_ups := self.suggestion_content.suggestions.get(q)) is not None:
            results_id, fkw_id = suggest_look_ups
            res = self.suggestion_content.results[results_id]
            is_sponsored = res.get("iab_category") == IABCategory.SHOPPING
            score = (
                self.score_wikipedia
                if (advertiser := res.get("advertiser")) == "Wikipedia"
                else self.score
            )
            suggestion_dict = {
                "block_id": res.get("id"),
                "full_keyword": self.suggestion_content.full_keywords[fkw_id],
                "title": res.get("title"),
                "url": res.get("url"),
                "impression_url": res.get("impression_url"),
                "click_url": res.get("click_url"),
                "provider": self.name,
                "advertiser": advertiser,
                "is_sponsored": is_sponsored,
                "icon": self.suggestion_content.icons.get(
                    int(res.get("icon", MISSING_ICON_ID))
                ),
                "score": score,
            }
            return [
                SponsoredSuggestion(**suggestion_dict)
                if is_sponsored
                else NonsponsoredSuggestion(**suggestion_dict)
            ]
        return []
