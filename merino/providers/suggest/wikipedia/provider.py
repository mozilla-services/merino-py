"""The provider for the dynamic Wikipedia integration."""

import asyncio
import logging
import time
from typing import Any, Final

from pydantic import HttpUrl

from merino.configs import settings
from merino.exceptions import BackendError
from merino.governance.circuitbreakers import WikipediaCircuitBreaker
from merino.providers.suggest.base import (
    BaseProvider,
    BaseSuggestion,
    SuggestionRequest,
    Category,
)
from merino.providers.suggest.wikipedia.backends.protocol import (
    EngagementData,
    WikipediaBackend,
)
from merino.utils.gcs.engagement.filemanager import KeywordEngagementFilemanager
from merino.providers.suggest.wikipedia.backends.utils import get_language_code
from merino.utils import cron

# The Wikipedia icon backed by Merino's image CDN.
# TODO: Use a better way to fetch this icon URL instead of hardcoding it here.
ICON: Final[str] = (
    "https://merino-images.services.mozilla.com/favicons/"
    "4c8bf96d667fa2e9f072bdd8e9f25c8ba6ba2ad55df1af7d9ea0dd575c12abee_1313.png"
)
ADVERTISER: Final[str] = "dynamic-wikipedia"
BLOCK_ID: Final[int] = 0

logger = logging.getLogger(__name__)


class WikipediaSuggestion(BaseSuggestion):
    """Model for dynamic Wikipedia suggestions.

    For backwards compatibility in Firefox, both `impression_url` and `click_url`
    are set to `None`. Likewise, `block_id` is set to 0 for now.
    """

    full_keyword: str
    advertiser: str
    block_id: int
    impression_url: HttpUrl | None = None
    click_url: HttpUrl | None = None


class Provider(BaseProvider):
    """Suggestion provider for Wikipedia through Elasticsearch."""

    backend: WikipediaBackend
    score: float
    title_block_list: set[str]
    engagement_data: EngagementData
    filemanager: KeywordEngagementFilemanager
    engagement_resync_interval_sec: float
    cron_interval_sec: float
    last_engagement_fetch_at: float
    engagement_cron_task: asyncio.Task

    def __init__(
        self,
        backend: WikipediaBackend,
        title_block_list: set[str],
        engagement_gcs_bucket: str,
        engagement_blob_name: str,
        engagement_resync_interval_sec: float,
        cron_interval_sec: float,
        name: str = "wikipedia",
        enabled_by_default: bool = True,
        query_timeout_sec: float = settings.providers.wikipedia.query_timeout_sec,
        score=settings.providers.wikipedia.score,
        **kwargs: Any,
    ) -> None:
        """Store the given Remote Settings backend on the provider."""
        self.backend = backend
        # Ensures block list checks are case insensitive.
        self.title_block_list = {entry.lower() for entry in title_block_list}
        self._name = name
        self._enabled_by_default = enabled_by_default
        self._query_timeout_sec = query_timeout_sec
        self.score = score
        self.engagement_data = EngagementData(wiki_aggregated={})
        self.engagement_resync_interval_sec = engagement_resync_interval_sec
        self.cron_interval_sec = cron_interval_sec
        self.last_engagement_fetch_at = 0
        self.filemanager = KeywordEngagementFilemanager(
            gcs_bucket_path=engagement_gcs_bucket,
            blob_name=engagement_blob_name,
        )
        super().__init__(**kwargs)

    async def initialize(self) -> None:
        """Initialize Wikipedia provider and start engagement data cron job."""
        engagement_cron_job = cron.Job(
            name="resync_wikipedia_engagement_data",
            interval=self.cron_interval_sec,
            condition=self._should_fetch_engagement,
            task=self._fetch_engagement_data,
        )
        self.engagement_cron_task = asyncio.create_task(engagement_cron_job())

    def _should_fetch_engagement(self) -> bool:
        """Check if it should fetch Wikipedia engagement data from GCS."""
        return (time.time() - self.last_engagement_fetch_at) >= self.engagement_resync_interval_sec

    async def _fetch_engagement_data(self) -> None:
        """Fetch Wikipedia engagement data from GCS and store it in memory.

        If the fetch returns no data, `last_engagement_fetch_at` is not updated
        so the cron job retries on the next tick.
        """
        try:
            data = await self.filemanager.get_file()
            if data is None:
                logger.warning(
                    "Wikipedia engagement data fetch returned None, will retry on next tick"
                )
                return
            self.engagement_data = EngagementData.model_validate(data.model_dump())
            self.last_engagement_fetch_at = time.time()
        except Exception as e:
            logger.warning(
                "Failed to fetch Wikipedia engagement data from GCS",
                extra={"error": str(e)},
            )

    def hidden(self) -> bool:  # noqa: D102
        """Whether this provider is hidden or not."""
        return False

    @WikipediaCircuitBreaker(name="wikipedia")
    async def query(self, srequest: SuggestionRequest) -> list[BaseSuggestion]:
        """Provide suggestion for a given query."""
        try:
            languages: list[str] = srequest.languages if srequest.languages else []
            language_code = get_language_code(languages)
            suggestions = await self.backend.search(srequest.query, language_code)
        except BackendError as e:
            logger.warning(f"{e}")
            raise

        return [
            WikipediaSuggestion(
                block_id=BLOCK_ID,
                advertiser=ADVERTISER,
                is_sponsored=False,
                icon=ICON,
                score=self.score,
                provider=self.name,
                categories=[Category.Education],
                **suggestion,
            )
            for suggestion in suggestions
            # Ensures titles that are in the block list are not returned as suggestions.
            if suggestion["title"].lower() not in self.title_block_list
        ]

    async def shutdown(self) -> None:
        """Override the shutdown handler."""
        return await self.backend.shutdown()
