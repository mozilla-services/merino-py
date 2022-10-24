"""AdM integration that uses the remote-settings provided data."""
import asyncio
import logging
import time
from asyncio import as_completed
from enum import Enum, unique
from typing import Any, Final, Optional, Protocol, cast

import httpx
from pydantic import HttpUrl

from merino import cron
from merino.config import settings
from merino.providers.base import BaseProvider, BaseSuggestion, SuggestionRequest

logger = logging.getLogger(__name__)


class RemoteSettingsBackend(Protocol):
    """Protocol for a Remote Settings backend that this provider depends on.

    Note: This only defines the methods used by the provider. The actual backend
    might define additional methods and attributes which this provider doesn't
    directly depend on.
    """

    async def get(
        self, bucket: str, collection: str
    ) -> list[dict[str, Any]]:  # pragma: no cover
        """Get records from Remote Settings."""
        ...

    async def fetch_attachment(
        self, attachment_uri: str
    ) -> httpx.Response:  # pragma: no cover
        """Fetch the attachment for the given URI."""
        ...

    def get_icon_url(self, icon_uri: str) -> str:  # pragma: no cover
        """Get the icon URL for the given URI."""
        ...


class TestBackend:
    """A test backend that always returns empty results for tests."""

    async def get(self, bucket: str, collection: str) -> list[dict[str, Any]]:
        """Return fake records."""
        return []

    async def fetch_attachment(self, attachment_uri: str) -> httpx.Response:
        """Return a fake attachment for the given URI."""
        return httpx.Response(200, text="")

    def get_icon_url(self, icon_uri: str) -> str:
        """Return a fake icon URL for the given URI."""
        return ""


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

    suggestions: dict[str, int] = {}
    results: list[dict[str, Any]] = []
    icons: dict[int, str] = {}
    # Store the value to avoid fetching it from settings every time as that'd
    # require a three-way dict lookup.
    score: float = settings.providers.adm.score
    last_fetch_at: float
    cron_task: asyncio.Task
    backend: RemoteSettingsBackend

    def __init__(
        self,
        backend: RemoteSettingsBackend,
        name: str = "adm",
        enabled_by_default: bool = True,
        **kwargs: Any,
    ) -> None:
        """Store the given Remote Settings backend on the provider."""
        self.backend = backend
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
            interval=settings.providers.adm.resync_interval_sec,
            condition=self._should_fetch,
            task=self._fetch,
        )
        # Store the created task on the instance variable. Otherwise it will get
        # garbage collected because asyncio's runtime only holds a weak
        # reference to it.
        self.cron_task = asyncio.create_task(cron_job())

    def _should_fetch(self) -> bool:
        """Check if it should fetch data from Remote Settings."""
        return cast(
            bool,
            time.time() - self.last_fetch_at
            >= settings.providers.adm.resync_interval_sec,
        )

    async def _fetch(self) -> None:
        """Fetch suggestions, keywords, and icons from Remote Settings."""
        # A dictionary keyed on suggestion keywords, each value stores an index
        # (pointer) to one entry of the suggestion result list.
        suggestions: dict[str, int] = {}
        # A list of suggestion results.
        results: list[dict[str, Any]] = []
        # A dictionary of icon IDs to icon URLs.
        icons: dict[int, str] = {}

        suggest_settings = await self.backend.get(
            settings.remote_settings.bucket, settings.remote_settings.collection
        )

        # Falls back to "data" records if "offline-expansion-data" records do not exist
        records = [
            record
            for record in suggest_settings
            if record["type"] == "offline-expansion-data"
        ] or [record for record in suggest_settings if record["type"] == "data"]

        fetch_tasks = [
            self.backend.fetch_attachment(item["attachment"]["location"])
            for item in records
        ]
        for done_task in as_completed(fetch_tasks):
            res = await done_task
            for suggestion in res.json():
                id = len(results)
                for kw in suggestion.pop("keywords", []):
                    # Note that for adM suggestions, each keyword can only be mapped to
                    # a single suggestion.
                    suggestions[kw] = id
                results.append(suggestion)
        icon_record = [
            record for record in suggest_settings if record["type"] == "icon"
        ]
        for icon in icon_record:
            id = int(icon["id"].replace("icon-", ""))
            icons[id] = self.backend.get_icon_url(icon["attachment"]["location"])

        # overwrite the instance variables
        self.suggestions = suggestions
        self.results = results
        self.icons = icons
        self.last_fetch_at = time.time()

    def hidden(self) -> bool:  # noqa: D102
        return False

    async def query(self, srequest: SuggestionRequest) -> list[BaseSuggestion]:
        """Provide suggestion for a given query."""
        q = srequest.query
        if (id := self.suggestions.get(q)) is not None:
            res = self.results[id]
            is_sponsored = res.get("iab_category") == IABCategory.SHOPPING
            suggestion_dict = {
                "block_id": res.get("id"),
                "full_keyword": q,
                "title": res.get("title"),
                "url": res.get("url"),
                "impression_url": res.get("impression_url"),
                "click_url": res.get("click_url"),
                "provider": self.name,
                "advertiser": res.get("advertiser"),
                "is_sponsored": is_sponsored,
                "icon": self.icons.get(int(res.get("icon", MISSING_ICON_ID))),
                "score": self.score,
            }
            return [
                SponsoredSuggestion(**suggestion_dict)
                if is_sponsored
                else NonsponsoredSuggestion(**suggestion_dict)
            ]
        return []
