"""AdM integration that uses the remote-settings provided data."""
import asyncio
import logging
import time
from asyncio import as_completed
from enum import Enum, unique
from typing import Any, Protocol

import httpx

from merino import cron
from merino.config import settings
from merino.providers.base import BaseProvider

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
        self, attachment_uri: Any
    ) -> httpx.Response:  # pragma: no cover
        """Fetch the attachment for the given URI."""
        ...

    def get_icon_url(self, icon_uri: str) -> str:  # pragma: no cover
        """Get the icon URL for the given URI."""
        ...


@unique
class IABCategory(str, Enum):
    """Enum for IAB categories.

    Suggestions with the category `SHOPPING` will be labelled as
    sponsored suggestions. Otherwise, they're nonsponsored.
    """

    SHOPPING = "22 - Shopping"
    EDUCATION = "5 - Education"


# Used whenever the `icon` field is missing from the suggestion payload.
MISSING_ICON_ID = "-1"


class Provider(BaseProvider):
    """Suggestion provider for adMarketplace through Remote Settings."""

    suggestions: dict[str, int] = {}
    results: list[dict[str, Any]] = []
    icons: dict[int, str] = {}
    last_fetch_at: float
    cron_task: asyncio.Task
    backend: RemoteSettingsBackend

    def __init__(self, backend: RemoteSettingsBackend, **kwargs: Any) -> None:
        """Store the given Remote Settings backend on the provider."""
        self.backend = backend
        super().__init__(**kwargs)

    async def initialize(self) -> None:
        """Initialize cron job."""
        await self._fetch()
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
        return (
            time.time() - self.last_fetch_at
            >= settings.providers.adm.resync_interval_sec
        )

    async def _fetch(self) -> None:
        """Fetch suggestions, keywords, and icons from Remote Settings."""
        suggestions: dict[str, int] = {}
        results: list[dict[str, Any]] = []
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
                for kw in suggestion.get("keywords"):
                    suggestions[kw] = id
                results.append(
                    {k: suggestion[k] for k in suggestion if k != "keywords"}
                )
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

    def enabled_by_default(self) -> bool:  # noqa: D102
        return True

    def hidden(self) -> bool:  # noqa: D102
        return False

    async def query(self, q: str) -> list[dict[str, Any]]:
        """Provide suggestion for a given query."""
        if (id := self.suggestions.get(q)) is not None:
            if (res := self.results[id]) is not None:
                return [
                    {
                        "block_id": res.get("id"),
                        "full_keyword": q,
                        "title": res.get("title"),
                        "url": res.get("url"),
                        "impression_url": res.get("impression_url"),
                        "click_url": res.get("click_url"),
                        "provider": "adm",
                        "advertiser": res.get("advertiser"),
                        "is_sponsored": res.get("iab_category") == IABCategory.SHOPPING,
                        "icon": self.icons.get(int(res.get("icon", MISSING_ICON_ID))),
                        "score": settings.providers.adm.score,
                    }
                ]
        return []
