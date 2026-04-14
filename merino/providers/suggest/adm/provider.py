"""AdM integration that provides sponsored suggestions."""

import asyncio
import logging
import time
from enum import Enum, unique
from typing import Any, Final, cast

import aiodogstatsd
from moz_merino_ext.amp import AmpIndexManager, PyAmpResult

from pydantic import HttpUrl

from merino.configs import settings
from merino.optimizers.models import EngagementMetrics, ThompsonCandidate
from merino.optimizers.thompson import ThompsonSampler
from merino.providers.suggest.adm.backends.protocol import EngagementData, FormFactor
from merino.utils.gcs.engagement.filemanager import EngagementFilemanager
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

FALLBACK_FORM_FACTOR: str = "other"
FALLBACK_COUNTRY_CODE: str = "US"
CLIENT_VARIANTS_ALLOW_LIST = frozenset(settings.web.api.v1.client_variant_allow_list)
TS_DRY_RUN: bool = settings.providers.adm.thompson.dry_run
ENGAGEMENT_GUIDED_SUGGESTIONS: str = settings.providers.adm.thompson.engagement_guided_suggestions


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
    """Suggestion provider for adMarketplace via Remote Settings or MARS."""

    suggestion_content: SuggestionContent
    # Store the value to avoid fetching it from settings every time as that'd
    # require a three-way dict lookup.
    score: float
    last_fetch_at: float
    cron_task: asyncio.Task
    backend: AdmBackend
    resync_interval_sec: float
    min_attempted_count: int
    should_check_client_variants: bool
    thompson: ThompsonSampler | None = None
    engagement_data: EngagementData
    filemanager: EngagementFilemanager
    engagement_resync_interval_sec: float
    last_engagement_fetch_at: float
    engagement_cron_task: asyncio.Task
    staleness_cron_task: asyncio.Task

    def __init__(
        self,
        backend: AdmBackend,
        metrics_client: aiodogstatsd.Client,
        score: float,
        name: str,
        resync_interval_sec: float,
        cron_interval_sec: float,
        engagement_gcs_bucket: str,
        engagement_blob_name: str,
        engagement_resync_interval_sec: float,
        enabled_by_default: bool = True,
        min_attempted_count: int = 0,
        thompson: ThompsonSampler | None = None,
        should_check_client_variants=True,
        **kwargs: Any,
    ) -> None:
        """Store the given Remote Settings backend on the provider."""
        self.backend = backend
        self.metrics_client = metrics_client
        self.score = score
        self.resync_interval_sec = resync_interval_sec
        self.cron_interval_sec = cron_interval_sec
        self.suggestion_content = SuggestionContent(index_manager=AmpIndexManager(), icons={})  # type: ignore[no-untyped-call]
        self._name = name
        self._enabled_by_default = enabled_by_default
        self.min_attempted_count = min_attempted_count
        self.thompson = thompson
        self.engagement_data = EngagementData(amp={}, amp_aggregated={})
        self.engagement_resync_interval_sec = engagement_resync_interval_sec
        self.last_engagement_fetch_at = 0
        self.filemanager = EngagementFilemanager(
            gcs_bucket_path=engagement_gcs_bucket,
            blob_name=engagement_blob_name,
        )
        self.should_check_client_variants = should_check_client_variants
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

        await self._fetch_engagement_data()
        engagement_cron_job = cron.Job(
            name="resync_engagement_data",
            interval=self.cron_interval_sec,
            condition=self._should_fetch_engagement,
            task=self._fetch_engagement_data,
        )
        self.engagement_cron_task = asyncio.create_task(engagement_cron_job())

        staleness_cron_job = cron.Job(
            name="mars_staleness_metric",
            interval=self.cron_interval_sec,
            condition=self._should_emit_staleness,
            task=self._emit_staleness,
        )
        self.staleness_cron_task = asyncio.create_task(staleness_cron_job())

    def _should_emit_staleness(self) -> bool:
        """Check if the backend tracks data staleness."""
        return getattr(self.backend, "last_new_data_at", 0) > 0

    async def _emit_staleness(self) -> None:
        """Emit the data staleness gauge for the MARS backend."""
        last_new_data_at: float = getattr(self.backend, "last_new_data_at", 0)
        if last_new_data_at > 0:
            staleness = time.time() - last_new_data_at
            self.metrics_client.gauge(
                "mars.data.staleness_seconds",
                value=staleness,
            )

    def _should_fetch(self) -> bool:
        """Check if it should fetch data from Remote Settings."""
        return (time.time() - self.last_fetch_at) >= self.resync_interval_sec

    def _should_fetch_engagement(self) -> bool:
        """Check if it should fetch engagement data from GCS."""
        return (time.time() - self.last_engagement_fetch_at) >= self.engagement_resync_interval_sec

    async def _fetch(self) -> None:
        """Fetch suggestions, keywords, and icons from Remote Settings."""
        self.suggestion_content = await self.backend.fetch()
        self.last_fetch_at = time.time()

    async def _fetch_engagement_data(self) -> None:
        """Fetch engagement data from GCS and store it in memory.

        If the fetch returns no data, `last_engagement_fetch_at` is not updated
        so the cron job retries on the next tick.
        """
        try:
            data = await self.filemanager.get_file()
            if data is None:
                logger.warning("Engagement data fetch returned None, will retry on next tick")
                return
            self.engagement_data = EngagementData.model_validate(data.model_dump())
            self.last_engagement_fetch_at = time.time()
        except Exception as e:
            logger.warning(
                "Failed to fetch engagement data from GCS",
                extra={"error": str(e)},
            )

    def hidden(self) -> bool:  # noqa: D102
        return False

    def normalize_query(self, query: str) -> str:
        """Convert a query string to lowercase and remove leading spaces."""
        return query.lstrip().lower()

    def _fetch_engagement_metrics(self, suggestion: PyAmpResult) -> EngagementMetrics:
        """Fetch engagement metrics for an AMP suggestion."""
        advertiser = suggestion.advertiser.lower()
        engaged, attempted = 1, 1
        if self.engagement_data and (metrics := self.engagement_data.amp.get(advertiser)):
            attempted = int(metrics.get("impressions", attempted))
            engaged = int(metrics.get("clicks", engaged))
        return EngagementMetrics(engaged=engaged, attempted=attempted)

    def _is_thompson_eligible(self, client_variants: list[str]) -> bool:
        """Return True if Thompson sampling should be applied to this request."""
        if not self.thompson:
            return False
        if not self.engagement_data.amp:
            return False
        if self.should_check_client_variants:
            return ENGAGEMENT_GUIDED_SUGGESTIONS in client_variants
        return True

    def _select(
        self, suggestions: list[PyAmpResult], client_variants: list[str]
    ) -> PyAmpResult | None:
        def _sampling() -> PyAmpResult | None:
            """Thompson sampling helper function."""
            candidates = [
                ThompsonCandidate(id=i, metrics=self._fetch_engagement_metrics(suggestion))
                for i, suggestion in enumerate(suggestions)
            ]

            tags = {}
            if suggestions:
                # FIXME(nanj): this uses the first element as the subject as `suggestions`
                # should always be a singleton list. Update it if that's false in the future.
                tags["subject"] = suggestions[0].advertiser.lower()

            # If it's the only candidate with an attempted count less than the threshold, skip sampling.
            if len(candidates) == 1 and candidates[0].metrics.attempted < self.min_attempted_count:
                self.metrics_client.increment(
                    "providers.adm.thompson.select", tags={"outcome": "skipped", **tags}
                )
                return suggestions[0]

            winner = cast(ThompsonSampler, self.thompson).sample(candidates)
            if winner:
                self.metrics_client.increment(
                    "providers.adm.thompson.select", tags={"outcome": "selected", **tags}
                )
                winner_idx: int = winner.id
                return suggestions[winner_idx]
            else:
                self.metrics_client.increment(
                    "providers.adm.thompson.select", tags={"outcome": "suppressed", **tags}
                )
                return None

        if self._is_thompson_eligible(client_variants):
            winner = _sampling()
            if not TS_DRY_RUN:
                return winner

        return suggestions[0] if suggestions else None

    async def query(self, srequest: SuggestionRequest) -> list[BaseSuggestion]:
        """Provide suggestion for a given query."""
        q: str = srequest.query
        form_factor = srequest.user_agent.form_factor if srequest.user_agent else None
        country = srequest.geolocation.country
        client_variants = srequest.client_variants

        # Set the fallback country code and form factor if absent. See "DISCO-3971" for details.
        form_factor = form_factor or FALLBACK_FORM_FACTOR
        country = country or FALLBACK_COUNTRY_CODE

        segment = (FORM_FACTORS_FALLBACK_MAPPING.get(form_factor, FormFactor.DESKTOP.value),)
        idx_id = f"{country}/{segment}"
        if (
            self.suggestion_content.index_manager.has(idx_id)
            and (suggestions := self.suggestion_content.index_manager.query(idx_id, q))
            and (res := self._select(suggestions, client_variants))
        ):
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
