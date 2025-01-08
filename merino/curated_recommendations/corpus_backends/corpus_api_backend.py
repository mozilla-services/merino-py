"""Corpus API backend for making GRAPHQL requests"""

import asyncio
import logging
import random
from datetime import datetime, timedelta
from urllib.parse import urlparse, urlencode, parse_qsl
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from dataclasses import dataclass

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
from merino.curated_recommendations.corpus_backends.protocol import (
    CorpusBackend,
    CorpusItem,
    Topic,
    ScheduledSurfaceId,
)
from merino.exceptions import BackendError
from merino.utils.version import fetch_app_version_from_file

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CacheKey:
    """Cache key for identifying cached items."""

    surface_id: ScheduledSurfaceId
    days_offset: int = 0


@dataclass
class CacheEntry:
    """Class to store cache-related data."""

    items: list[CorpusItem]
    expiration: datetime
    lock: asyncio.Lock


class CorpusGraphQLError(BackendError):
    """Error during interaction with the corpus GraphQL API."""


class CorpusApiGraphConfig:
    """Corpus API Graph Config."""

    CORPUS_API_PROD_ENDPOINT = "https://client-api.getpocket.com"
    CORPUS_API_DEV_ENDPOINT = "https://client-api.getpocket.dev"

    def __init__(self) -> None:
        self._app_version = fetch_app_version_from_file().commit

    @property
    def endpoint(self) -> str:
        """Pocket GraphQL endpoint URL"""
        return self.CORPUS_API_PROD_ENDPOINT

    @property
    def headers(self) -> dict[str, str]:
        """Pocket GraphQL client headers"""
        return {
            "apollographql-client-name": "merino-py",
            "apollographql-client-version": self._app_version,
        }


"""
Map Corpus topic to a SERP topic.
Note: Not all Corpus topics map to a SERP topic. For unmapped topics, null is returned.
See: https://mozilla-hub.atlassian.net/wiki/spaces/MozSocial/pages/735248385/Topic+Selection+Tech+Spec+Draft#Topics  # noqa
"""
CORPUS_TOPIC_TO_SERP_TOPIC_MAPPING = {
    "BUSINESS": Topic.BUSINESS,
    "CAREER": Topic.CAREER,
    "EDUCATION": Topic.EDUCATION,
    "ENTERTAINMENT": Topic.ARTS,
    "FOOD": Topic.FOOD,
    "GAMING": Topic.GAMING,
    "HEALTH_FITNESS": Topic.HEALTH_FITNESS,
    "HOME": Topic.HOME,
    "PARENTING": Topic.PARENTING,
    "PERSONAL_FINANCE": Topic.PERSONAL_FINANCE,
    "POLITICS": Topic.POLITICS,
    "SCIENCE": Topic.SCIENCE,
    "SELF_IMPROVEMENT": Topic.SELF_IMPROVEMENT,
    "SPORTS": Topic.SPORTS,
    "TECHNOLOGY": Topic.TECHNOLOGY,
    "TRAVEL": Topic.TRAVEL,
}

"""
Set utm_source for specific ScheduledSurfaceId.
For ids not in the table, null is returned.
"""
SCHEDULED_SURFACE_ID_TO_UTM_SOURCE: dict[ScheduledSurfaceId, str] = {
    ScheduledSurfaceId.NEW_TAB_EN_US: "firefox-newtab-en-us",
    ScheduledSurfaceId.NEW_TAB_EN_GB: "firefox-newtab-en-gb",
    ScheduledSurfaceId.NEW_TAB_EN_INTL: "firefox-newtab-en-intl",
    ScheduledSurfaceId.NEW_TAB_DE_DE: "firefox-newtab-de-de",
    ScheduledSurfaceId.NEW_TAB_ES_ES: "firefox-newtab-es-es",
    ScheduledSurfaceId.NEW_TAB_FR_FR: "firefox-newtab-fr-fr",
    ScheduledSurfaceId.NEW_TAB_IT_IT: "firefox-newtab-it-it",
}


class CorpusApiBackend(CorpusBackend):
    """Corpus API Backend hitting the curated corpus api
    & returning recommendations for a date & locale/region.
    Uses an in-memory cache and request coalescing to limit request rate to the backend.
    """

    http_client: AsyncClient
    graph_config: CorpusApiGraphConfig
    metrics_client: aiodogstatsd.Client

    # time-to-live was chosen because 1 minute (+/- 10 s) is short enough that updates by curators
    # such as breaking news or editorial corrections propagate fast enough, and that the request
    # rate to the scheduledSurface query stays close to the historic rate of ~100 requests/minute.
    cache_time_to_live_min = timedelta(seconds=50)
    cache_time_to_live_max = timedelta(seconds=70)
    _cache: dict[CacheKey, CacheEntry]
    _background_tasks: set[asyncio.Task]

    def __init__(
        self,
        http_client: AsyncClient,
        graph_config: CorpusApiGraphConfig,
        metrics_client: aiodogstatsd.Client,
    ):
        self.http_client = http_client
        self.graph_config = graph_config
        self.metrics_client = metrics_client
        self._cache = {}
        self._background_tasks = set()

    @staticmethod
    def map_corpus_topic_to_serp_topic(topic: str) -> Topic | None:
        """Map the corpus topic to the SERP topic."""
        return CORPUS_TOPIC_TO_SERP_TOPIC_MAPPING.get(topic.upper())

    @staticmethod
    def get_utm_source(scheduled_surface_id: ScheduledSurfaceId) -> str | None:
        """Return utm_source value to attribute curated recommendations to, based on the
        scheduled_surface_id.
        https://github.com/Pocket/recommendation-api/blob/main/app/data_providers/slate_providers/slate_provider.py#L95C5-L100C46
        """
        return SCHEDULED_SURFACE_ID_TO_UTM_SOURCE.get(scheduled_surface_id)

    @staticmethod
    def update_url_utm_source(url: str, utm_source: str) -> str:
        """Return an updated url where utm_source query param was added or replaced."""
        utm_source_param = {"utm_source": utm_source}

        # parse url into 6 parts
        parsed_url = urlparse(url)
        # get the query params as a dict
        query = dict(parse_qsl(parsed_url.query))
        # add the utm_source param to query
        query.update(utm_source_param)
        # add / replace utm_source with new utm_source param & return updated url
        updated_url = parsed_url._replace(query=urlencode(query)).geturl()
        return updated_url

    @staticmethod
    def get_surface_timezone(scheduled_surface_id: ScheduledSurfaceId) -> ZoneInfo:
        """Return the correct timezone for a scheduled surface id.
        If no timezone is found, gracefully return timezone in UTC.
        https://github.com/Pocket/recommendation-api/blob/main/app/data_providers/corpus/corpus_api_client.py#L98 # noqa
        """
        zones = {
            ScheduledSurfaceId.NEW_TAB_EN_US: "America/New_York",
            ScheduledSurfaceId.NEW_TAB_EN_GB: "Europe/London",
            # Note: en-Intl is poorly named. Only India is currently eligible.
            ScheduledSurfaceId.NEW_TAB_EN_INTL: "Asia/Kolkata",
            ScheduledSurfaceId.NEW_TAB_DE_DE: "Europe/Berlin",
            ScheduledSurfaceId.NEW_TAB_ES_ES: "Europe/Madrid",
            ScheduledSurfaceId.NEW_TAB_FR_FR: "Europe/Paris",
            ScheduledSurfaceId.NEW_TAB_IT_IT: "Europe/Rome",
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

    async def fetch(
        self, surface_id: ScheduledSurfaceId, days_offset: int = 0
    ) -> list[CorpusItem]:
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
        now = datetime.now()
        cache_key = CacheKey(surface_id, days_offset)

        # If we have expired cached data, revalidate asynchronously without waiting for the result.
        if cache_key in self._cache:
            cache_entry = self._cache[cache_key]
            if now >= cache_entry.expiration:
                task = asyncio.create_task(self._revalidate_cache(surface_id, days_offset))
                # Save a reference to the result of this function, to avoid a task disappearing
                # mid-execution. The event loop only keeps weak references to tasks. A task that
                # isn’t referenced elsewhere may get garbage collected, even before it’s done.
                # https://docs.python.org/3/library/asyncio-task.html#asyncio.create_task
                self._background_tasks.add(task)
                task.add_done_callback(self._background_tasks.discard)
            return cache_entry.items

        # If no cache value exists, fetch new data and await the result.
        return await self._revalidate_cache(surface_id, days_offset)

    @retry(
        wait=wait_exponential_jitter(
            initial=settings.curated_recommendations.corpus_api.retry_wait_initial_seconds,
            jitter=settings.curated_recommendations.corpus_api.retry_wait_jitter_seconds,
        ),
        stop=stop_after_attempt(settings.curated_recommendations.corpus_api.retry_count),
        retry=retry_if_exception_type((CorpusGraphQLError, HTTPError, ValueError)),
        reraise=True,  # Raise the exception our code encountered, instead of a RetryError
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    async def _fetch_from_backend(
        self, surface_id: ScheduledSurfaceId, days_offset: int
    ) -> list[CorpusItem]:
        """Issue a scheduledSurface query"""
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

        with self.metrics_client.timeit("corpus_api.request.timing"):
            res = await self.http_client.post(
                self.graph_config.endpoint,
                json=body,
                headers=self.graph_config.headers,
            )
        self.metrics_client.increment(f"corpus_api.request.status_codes.{res.status_code}")

        res.raise_for_status()
        data = res.json()

        if res.status_code == 200 and "errors" in data:
            self.metrics_client.increment("corpus_api.request.graphql_error")
            raise CorpusGraphQLError(
                f"curated-corpus-api returned GraphQL errors {data['errors']}"
            )

        # get the utm_source based on scheduled surface id
        utm_source = self.get_utm_source(surface_id)

        for item in data["data"]["scheduledSurface"]["items"]:
            # Map Corpus topic to SERP topic
            item["corpusItem"]["topic"] = self.map_corpus_topic_to_serp_topic(
                item["corpusItem"]["topic"]
            )
            # Update url (add / replace utm_source query param)
            item["corpusItem"]["url"] = self.update_url_utm_source(
                item["corpusItem"]["url"], str(utm_source)
            )

        curated_recommendations = [
            CorpusItem(
                **item["corpusItem"],
                corpusItemId=item["corpusItem"]["id"],
                scheduledCorpusItemId=item["id"],
            )
            for item in data["data"]["scheduledSurface"]["items"]
        ]

        return curated_recommendations

    async def _revalidate_cache(
        self, surface_id: ScheduledSurfaceId, days_offset: int
    ) -> list[CorpusItem]:
        """Update the cache for a specific surface and return the corpus items.
        If the API fails to respond successfully even after retries, return the latest cached data.
        Only a single "coalesced" request will be made to the backend per surface id.
        """
        cache_key = CacheKey(surface_id, days_offset)

        if cache_key not in self._cache:
            self._cache[cache_key] = CacheEntry([], datetime.min, asyncio.Lock())

        async with self._cache[cache_key].lock:
            # Check if the cache was updated while waiting for the lock.
            if datetime.now() < self._cache[cache_key].expiration:
                return self._cache[cache_key].items

            # Attempt to fetch new data from the backend
            try:
                data = await self._fetch_from_backend(surface_id, days_offset)
                self._cache[cache_key] = CacheEntry(
                    data, self.get_expiration_time(), asyncio.Lock()
                )
                return data
            except Exception as e:
                if self._cache[cache_key].items:
                    logger.error(
                        f"Failed to update corpus cache: {e}. Returning stale cached data."
                    )
                    return self._cache[cache_key].items
                else:
                    raise e

    @staticmethod
    def get_expiration_time() -> datetime:
        """Return the date & time when a cached value should be expired."""
        # Random jitter ensures that backend requests don't all happen at the same time.
        time_to_live_seconds = random.uniform(
            CorpusApiBackend.cache_time_to_live_min.total_seconds(),
            CorpusApiBackend.cache_time_to_live_max.total_seconds(),
        )
        return datetime.now() + timedelta(seconds=time_to_live_seconds)
