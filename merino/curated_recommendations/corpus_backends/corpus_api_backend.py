"""Corpus API backend for making GRAPHQL requests"""

from datetime import datetime, timedelta
import asyncio

from httpx import AsyncClient

from merino.curated_recommendations.corpus_backends.protocol import (
    CorpusBackend,
    CorpusItem,
    Topic,
    ScheduledSurfaceId,
)
from merino.utils.version import fetch_app_version_from_file


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
    "entertainment": Topic.ARTS.value,
    "food": Topic.FOOD.value,
    "science": Topic.EDUCATION.value,
    "health_fitness": Topic.HEALTH.value,
    "personal_finance": Topic.FINANCE.value,
    "politics": Topic.GOVERNMENT.value,
    "self_improvement": Topic.SOCIETY.value,
    "technology": Topic.TECH.value,
    "business": Topic.BUSINESS.value,
    "travel": Topic.TRAVEL.value,
    "sports": Topic.SPORTS.value,
}


def map_corpus_topic_to_serp_topic(topic: str) -> tuple[str] | None:
    """Map the corpus topic to the SERP topic."""
    return CORPUS_TOPIC_TO_SERP_TOPIC_MAPPING.get(topic.lower())


class CorpusApiBackend(CorpusBackend):
    """Corpus API Backend hitting the curated corpus api
    & returning recommendations for current date & locale/region.
    Uses an in-memory cache and request coalescing to limit request rate to the backend.
    """

    http_client: AsyncClient

    cache_expiration_time = timedelta(minutes=1)
    _cache: dict[ScheduledSurfaceId, list[CorpusItem]]
    _expirations: dict[ScheduledSurfaceId, datetime]
    _locks: dict[ScheduledSurfaceId, asyncio.Lock]

    def __init__(self, http_client: AsyncClient):
        self.http_client = http_client
        self._cache = {}
        self._expirations = {}
        self._locks = {}

    async def fetch(self, surface_id: ScheduledSurfaceId) -> list[CorpusItem]:
        """Fetch corpus items with stale-while-revalidate caching and request coalescing."""
        now = datetime.now()
        cache_key = surface_id

        # If we have expired cached data, revalidate asynchronously without waiting for the result.
        if cache_key in self._cache:
            if now >= self._expirations[cache_key]:
                asyncio.create_task(self._revalidate_cache(surface_id))  # noqa: should not 'await'

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

        # TODO: [MC-1199] The date is supposed to progress at 3am local time,
        # where 'local time' is based on the timezone associated with the scheduled surface.
        # This requirement is documented in the NewTab slate spec:
        # https://getpocket.atlassian.net/wiki/spaces/PE/pages/2927100008/Fx+NewTab+Slate+spec
        today = datetime.now()

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
            data = await self._fetch_from_backend(surface_id)
            self._cache[cache_key] = data
            self._expirations[cache_key] = datetime.now() + self.cache_expiration_time
            return data
