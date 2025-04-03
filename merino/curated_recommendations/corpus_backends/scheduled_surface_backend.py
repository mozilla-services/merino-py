"""Corpus API backend for making GRAPHQL requests"""

import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import aiodogstatsd
from httpx import AsyncClient, HTTPError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
    before_sleep_log,
)

from merino.configs import settings
from merino.curated_recommendations.corpus_backends.caching import (
    stale_while_revalidate,
    WaitRandomExpiration,
)
from merino.curated_recommendations.corpus_backends.protocol import (
    ScheduledSurfaceProtocol,
    CorpusItem,
    SurfaceId,
)
from merino.curated_recommendations.corpus_backends.utils import (
    get_utm_source,
    CorpusGraphQLError,
    CorpusApiGraphConfig,
    build_corpus_item,
)
from merino.providers.manifest import Provider as ManifestProvider

logger = logging.getLogger(__name__)


class ScheduledSurfaceBackend(ScheduledSurfaceProtocol):
    """Corpus API Backend hitting the curated corpus api
    & returning recommendations for a date & locale/region.
    Uses an in-memory cache and request coalescing to limit request rate to the backend.
    """

    http_client: AsyncClient
    graph_config: CorpusApiGraphConfig
    metrics_client: aiodogstatsd.Client
    manifest_provider: ManifestProvider

    # Time-to-live was chosen because 1 minute (+/- 10 s) is short enough that updates by curators
    # such as breaking news or editorial corrections propagate fast enough, and that the request
    # rate to the scheduledSurface query stays close to the historic rate of ~100 requests/minute.
    cache_time_to_live_min = timedelta(seconds=50)
    cache_time_to_live_max = timedelta(seconds=70)
    _cache: dict
    _background_tasks: set[asyncio.Task]

    def __init__(
        self,
        http_client: AsyncClient,
        graph_config: CorpusApiGraphConfig,
        metrics_client: aiodogstatsd.Client,
        manifest_provider: ManifestProvider,
    ):
        """Initialize the ScheduledCorpusBackend."""
        self.http_client = http_client
        self.graph_config = graph_config
        self.metrics_client = metrics_client
        self.manifest_provider = manifest_provider
        self._cache = {}
        self._background_tasks = set()

    @staticmethod
    def get_surface_timezone(scheduled_surface_id: SurfaceId) -> ZoneInfo:
        """Return the correct timezone for a scheduled surface id.
        If no timezone is found, gracefully return timezone in UTC.
        https://github.com/Pocket/recommendation-api/blob/main/app/data_providers/corpus/corpus_api_client.py#L98 # noqa
        """
        zones = {
            SurfaceId.NEW_TAB_EN_US: "America/New_York",
            SurfaceId.NEW_TAB_EN_GB: "Europe/London",
            # Note: en-Intl is poorly named. Only India is currently eligible.
            SurfaceId.NEW_TAB_EN_INTL: "Asia/Kolkata",
            SurfaceId.NEW_TAB_DE_DE: "Europe/Berlin",
            SurfaceId.NEW_TAB_ES_ES: "Europe/Madrid",
            SurfaceId.NEW_TAB_FR_FR: "Europe/Paris",
            SurfaceId.NEW_TAB_IT_IT: "Europe/Rome",
        }

        try:
            return ZoneInfo(zones[scheduled_surface_id])
        except (KeyError, ZoneInfoNotFoundError) as e:
            # Graceful degradation: continue to serve recommendations if timezone cannot be obtained
            # for the surface.
            default_tz = ZoneInfo("UTC")
            logging.error(
                f"Failed to get timezone for {scheduled_surface_id}, "
                f"so defaulting to {default_tz}: {e}"
            )
            return default_tz

    @staticmethod
    def get_scheduled_surface_date(surface_timezone: ZoneInfo) -> datetime:
        """Return scheduled surface date based on timezone."""
        return datetime.now(tz=surface_timezone) - timedelta(hours=3)

    @stale_while_revalidate(
        wait_expiration=WaitRandomExpiration(cache_time_to_live_min, cache_time_to_live_max),
        cache=lambda self: self._cache,
        jobs=lambda self: self._background_tasks,
    )
    @retry(
        wait=wait_exponential_jitter(
            initial=settings.curated_recommendations.corpus_api.retry_wait_initial_seconds,
            jitter=settings.curated_recommendations.corpus_api.retry_wait_jitter_seconds,
        ),
        stop=stop_after_attempt(settings.curated_recommendations.corpus_api.retry_count),
        retry=retry_if_exception_type((CorpusGraphQLError, HTTPError, ValueError)),
        reraise=True,
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    async def fetch(self, surface_id: SurfaceId, days_offset: int = 0) -> list[CorpusItem]:
        """Fetch corpus items with stale-while-revalidate caching and request coalescing.

        Stale-while-revalidate caching serves cached data while asynchronously refreshing it in the
        background. This accepts slightly outdated data while the cache is being refreshed, to
        ensures consistently quick responses without blocking the request.

        Request coalescing merges multiple identical requests made concurrently, ensuring that only
        one request is made, and thereby reducing load on the backend.

        Args:
            surface_id: Identifies the scheduled surface, for example NEW_TAB_EN_US.
            days_offset: Optionally, the number of days relative to today for which items were
                scheduled. A positive value indicates a future day, negative value indicates a past
                day, and 0 refers to today. Defaults to 0.

        Returns:
            list[CorpusItem]: A list of fetched corpus items.
        """
        query = """
            query ScheduledSurface($scheduledSurfaceId: ID!, $date: Date!) {
              scheduledSurface(id: $scheduledSurfaceId) {
                items: items(date: $date) {
                  id
                  corpusItem {
                    id
                    url
                    title
                    excerpt
                    topic
                    publisher
                    isTimeSensitive
                    imageUrl
                  }
                }
              }
            }
        """

        # Calculate the base date and adjusted date based on days_since_today
        today = self.get_scheduled_surface_date(self.get_surface_timezone(surface_id))
        adjusted_date = today + timedelta(days=days_offset)

        body = {
            "query": query,
            "variables": {
                "scheduledSurfaceId": surface_id,
                "date": adjusted_date.strftime("%Y-%m-%d"),
            },
        }
        with self.metrics_client.timeit("corpus_api.scheduled_surface.timing"):
            res = await self.http_client.post(
                self.graph_config.endpoint,
                json=body,
                headers=self.graph_config.headers,
            )

        self.metrics_client.increment(
            f"corpus_api.scheduled_surface.status_codes.{res.status_code}"
        )
        res.raise_for_status()
        data = res.json()

        if "errors" in data:
            self.metrics_client.increment("corpus_api.scheduled_surface.graphql_error")
            raise CorpusGraphQLError(
                f"curated-corpus-api returned GraphQL errors {data['errors']}"
            )

        utm_source = get_utm_source(surface_id)
        curated_recommendations = []
        for scheduled_item in data["data"]["scheduledSurface"]["items"]:
            corpus_item = build_corpus_item(
                corpus_item=scheduled_item["corpusItem"],
                manifest_provider=self.manifest_provider,
                utm_source=utm_source,
            )
            corpus_item = corpus_item.model_copy(
                update={"scheduledCorpusItemId": scheduled_item["id"]}
            )
            curated_recommendations.append(corpus_item)

        return curated_recommendations
