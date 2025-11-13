"""AdM integration that uses the remote-settings provided data."""

import asyncio
import logging
import time
from enum import Enum, unique
from typing import Any, Final

from moz_merino_ext.amp import AmpIndexManager

from pydantic import HttpUrl

from merino.providers.suggest.adm.backends.remotesettings import FormFactor
from merino.utils import cron
from merino.providers.suggest.adm.backends.protocol import AdmBackend, SuggestionContent
from merino.providers.suggest.base import (
    BaseProvider,
    BaseSuggestion,
    SuggestionRequest,
)

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
FORM_FACTORS_FALLBACK_MAPPING = {
    "other": FormFactor.DESKTOP.value,
    "tablet": FormFactor.PHONE.value,
    "desktop": FormFactor.DESKTOP.value,
    "phone": FormFactor.PHONE.value,
}


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
    impression_url: HttpUrl | None = None
    click_url: HttpUrl | None = None


class Provider(BaseProvider):
    """Suggestion provider for adMarketplace through Remote Settings."""

    suggestion_content: SuggestionContent
    # Store the value to avoid fetching it from settings every time as that'd
    # require a three-way dict lookup.
    score: float
    last_fetch_at: float
    cron_task: asyncio.Task
    backend: AdmBackend
    resync_interval_sec: float

    def __init__(
        self,
        backend: AdmBackend,
        score: float,
        name: str,
        resync_interval_sec: float,
        cron_interval_sec: float,
        enabled_by_default: bool = True,
        **kwargs: Any,
    ) -> None:
        """Store the given Remote Settings backend on the provider."""
        self.backend = backend
        self.score = score
        self.resync_interval_sec = resync_interval_sec
        self.cron_interval_sec = cron_interval_sec
        self.suggestion_content = SuggestionContent(index_manager=AmpIndexManager(), icons={})  # type: ignore[no-untyped-call]
        self.provider_id = name
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
            interval=self.cron_interval_sec,
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
        """Convert a query string to lowercase and remove leading spaces."""
        return query.lstrip().lower()

    async def query(self, srequest: SuggestionRequest) -> list[BaseSuggestion]:
        """Provide suggestion for a given query."""
        q: str = srequest.query
        form_factor = srequest.user_agent.form_factor if srequest.user_agent else None
        country = srequest.geolocation.country
        if country and form_factor:
            segment = (FORM_FACTORS_FALLBACK_MAPPING.get(form_factor, FormFactor.DESKTOP.value),)
            idx_id = f"{country}/{segment}"
            if self.suggestion_content.index_manager.has(idx_id) and (
                suggest_look_ups := self.suggestion_content.index_manager.query(idx_id, q)
            ):
                res = suggest_look_ups[0]

                is_sponsored = res.iab_category == IABCategory.SHOPPING

                url: str = res.url

                suggestion_dict: dict[str, Any] = {
                    "block_id": res.block_id,
                    "full_keyword": res.full_keyword,
                    "title": res.title,
                    "url": url,
                    "categories": res.serp_categories,
                    "impression_url": res.impression_url,
                    "click_url": res.click_url,
                    "provider": self.name,
                    "advertiser": res.advertiser,
                    "is_sponsored": is_sponsored,
                    "icon": self.suggestion_content.icons.get(res.icon, MISSING_ICON_ID),
                    "score": self.score,
                }
                return [
                    (
                        SponsoredSuggestion(**suggestion_dict)
                        if is_sponsored
                        else NonsponsoredSuggestion(**suggestion_dict)
                    )
                ]
        return []
