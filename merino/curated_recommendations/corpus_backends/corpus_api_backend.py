"""Corpus API backend for making GRAPHQL requests"""

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import logging
import random
from datetime import datetime, timedelta
import asyncio

from httpx import AsyncClient, HTTPError

from merino.curated_recommendations.corpus_backends.protocol import (
    CorpusBackend,
    CorpusItem,
    Topic,
    ScheduledSurfaceId,
)
from merino.utils.version import fetch_app_version_from_file

logger = logging.getLogger(__name__)


class CorpusApiGraphConfig:
    """Corpus API Graph Config."""

    CORPUS_API_PROD_ENDPOINT = "https://client-api.getpocket.com"
    CORPUS_API_DEV_ENDPOINT = "https://client-api.getpocket.dev"
    CLIENT_NAME = "merino-py"
    CLIENT_VERSION = fetch_app_version_from_file().commit
    HEADERS = {
        "apollographql-client-name": CLIENT_NAME,
        "apollographql-client-version": CLIENT_VERSION,
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
    "PARENTING": Topic.PARENTING,
    "PERSONAL_FINANCE": Topic.PERSONAL_FINANCE,
    "POLITICS": Topic.POLITICS,
    "SCIENCE": Topic.SCIENCE,
    "SELF_IMPROVEMENT": Topic.SELF_IMPROVEMENT,
    "SPORTS": Topic.SPORTS,
    "TECHNOLOGY": Topic.TECHNOLOGY,
    "TRAVEL": Topic.TRAVEL,
}


def map_corpus_topic_to_serp_topic(topic: str) -> Topic | None:
    """Map the corpus topic to the SERP topic."""
    return CORPUS_TOPIC_TO_SERP_TOPIC_MAPPING.get(topic.upper())


class CorpusApiBackend(CorpusBackend):
    """Corpus API Backend hitting the curated corpus api
    & returning recommendations for current date & locale/region.
    Uses an in-memory cache and request coalescing to limit request rate to the backend.
    """

    http_client: AsyncClient

    # time-to-live was chosen because 1 minute (+/- 10 s) is short enough that updates by curators
    # such as breaking news or editorial corrections propagate fast enough, and that the request
    # rate to the scheduledSurface query stays close to the historic rate of ~100 requests/minute.
    cache_time_to_live_min = timedelta(seconds=50)
    cache_time_to_live_max = timedelta(seconds=70)
    # The backoff time is the time that is waited before retrying.
    # fetch() makes a single retry attempt, so there's exponential backoff (for now).
    _backoff_time = timedelta(seconds=0.5)
    _cache: dict[ScheduledSurfaceId, list[CorpusItem]]
    _expirations: dict[ScheduledSurfaceId, datetime]
    _locks: dict[ScheduledSurfaceId, asyncio.Lock]
    _background_tasks: set[asyncio.Task]

    def __init__(self, http_client: AsyncClient):
        self.http_client = http_client
        self._cache = {}
        self._expirations = {}
        self._locks = {}
        self._background_tasks = set()

    @staticmethod
    def get_surface_timezone(scheduled_surface_id: str) -> ZoneInfo:
        """Return the correct timezone for a scheduled surface id.
        If no timezone is found, gracefully return timezone in UTC.
        https://github.com/Pocket/recommendation-api/blob/main/app/data_providers/corpus/corpus_api_client.py#L98 # noqa
        """
        zones = {
            "NEW_TAB_EN_US": "America/New_York",
            "NEW_TAB_EN_GB": "Europe/London",
            "NEW_TAB_EN_INTL": "Asia/Kolkata",  # Note: en-Intl is poorly named. Only India is currently eligible.
            "NEW_TAB_DE_DE": "Europe/Berlin",
            "NEW_TAB_ES_ES": "Europe/Madrid",
            "NEW_TAB_FR_FR": "Europe/Paris",
            "NEW_TAB_IT_IT": "Europe/Rome",
        }

        try:
            return ZoneInfo(zones[scheduled_surface_id])
        except (KeyError, ZoneInfoNotFoundError) as e:
            # Graceful degradation: continue to serve recommendations if timezone cannot be obtained for the surface.
            default_tz = ZoneInfo("UTC")
            logging.error(
                f"Failed to get timezone for {scheduled_surface_id}, so defaulting to {default_tz}: {e}"
            )
            return default_tz

    @staticmethod
    def get_scheduled_surface_date(surface_timezone: ZoneInfo) -> datetime:
        """Return scheduled surface date based on timezone."""
        return datetime.now(tz=surface_timezone) - timedelta(hours=3)

    async def fetch(self, surface_id: ScheduledSurfaceId) -> list[CorpusItem]:
        """Fetch corpus items with stale-while-revalidate caching and request coalescing."""
        now = datetime.now()
        cache_key = surface_id

        # If we have expired cached data, revalidate asynchronously without waiting for the result.
        if cache_key in self._cache:
            if now >= self._expirations[cache_key]:
                task = asyncio.create_task(self._revalidate_cache(surface_id))  # noqa: should not 'await'
                # Save a reference to the result of this function, to avoid a task disappearing
                # mid-execution. The event loop only keeps weak references to tasks. A task that
                # isn’t referenced elsewhere may get garbage collected, even before it’s done.
                # https://docs.python.org/3/library/asyncio-task.html#asyncio.create_task
                self._background_tasks.add(task)
                task.add_done_callback(self._background_tasks.discard)

            return self._cache[cache_key]

        # If no cache value exists, fetch new data and await the result.
        return await self._revalidate_cache(surface_id)

    async def _fetch_from_backend(self, surface_id: ScheduledSurfaceId) -> list[CorpusItem]:
        """Issue a scheduledSurface query"""
        query = """
            query ScheduledSurface($scheduledSurfaceId: ID!, $date: Date!) {
              scheduledSurface(id: $scheduledSurfaceId) {
                items: items(date: $date) {
                  id
                  corpusItem {
                    url
                    title
                    excerpt
                    topic
                    publisher
                    imageUrl
                  }
                }
              }
            }
        """

        # The date is supposed to progress at 3am local time,
        # where 'local time' is based on the timezone associated with the scheduled surface.
        # This requirement is documented in the NewTab slate spec:
        # https://getpocket.atlassian.net/wiki/spaces/PE/pages/2927100008/Fx+NewTab+Slate+spec
        today = self.get_scheduled_surface_date(self.get_surface_timezone(surface_id))

        body = {
            "query": query,
            "variables": {
                "scheduledSurfaceId": surface_id,
                "date": today.strftime("%Y-%m-%d"),
            },
        }

        res = await self.http_client.post(
            CorpusApiGraphConfig.CORPUS_API_PROD_ENDPOINT,
            json=body,
            headers=CorpusApiGraphConfig.HEADERS,
        )

        res.raise_for_status()
        data = res.json()

        # Map Corpus topic to SERP topic
        for item in data["data"]["scheduledSurface"]["items"]:
            item["corpusItem"]["topic"] = map_corpus_topic_to_serp_topic(
                item["corpusItem"]["topic"]
            )

        curated_recommendations = [
            CorpusItem(**item["corpusItem"], scheduledCorpusItemId=item["id"])
            for item in data["data"]["scheduledSurface"]["items"]
        ]
        return curated_recommendations

    async def _revalidate_cache(self, surface_id: ScheduledSurfaceId) -> list[CorpusItem]:
        """Purge and update the cache for a specific surface."""
        cache_key = surface_id

        if cache_key not in self._locks:
            self._locks[cache_key] = asyncio.Lock()

        async with self._locks[cache_key]:
            # Check if the cache was updated while waiting for the lock.
            if cache_key in self._cache and datetime.now() < self._expirations[cache_key]:
                return self._cache[cache_key]

            # Fetch new data from the backend.
            try:
                data = await self._fetch_from_backend(surface_id)
            except HTTPError as e:
                logger.warning(f"Retrying CorpusApiBackend._fetch_from_backend once after {e}")
                # Backoff prevents high API rate during downtime.
                await asyncio.sleep(self._backoff_time.total_seconds())
                # http errors are expected to be rare, so a single retry attempt probably suffices.
                data = await self._fetch_from_backend(surface_id)
            except Exception as e:
                # Backoff prevents high API rate when an unforeseen error occurs.
                await asyncio.sleep(self._backoff_time.total_seconds())
                raise e

            self._cache[cache_key] = data
            self._expirations[cache_key] = self.get_expiration_time()
            return data

    @staticmethod
    def get_expiration_time() -> datetime:
        """Return the date & time when a cached value should be expired."""
        # Random jitter ensures that backend requests don't all happen at the same time.
        time_to_live_seconds = random.uniform(
            CorpusApiBackend.cache_time_to_live_min.total_seconds(),
            CorpusApiBackend.cache_time_to_live_max.total_seconds(),
        )
        return datetime.now() + timedelta(seconds=time_to_live_seconds)
