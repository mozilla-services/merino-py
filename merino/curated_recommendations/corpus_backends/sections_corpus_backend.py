"""Corpus Sections API backend for fetching section recommendations using the getSections GraphQL query."""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

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
    SectionsCorpusProtocol,
    CorpusSection,
    ScheduledSurfaceId,
)
from merino.providers.manifest import Provider as ManifestProvider
from merino.curated_recommendations.corpus_backends.utils import (
    get_utm_source,
    get_expiration_time,
    build_corpus_item,
    CorpusGraphQLError,
    CorpusApiGraphConfig,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CacheKey:
    """Cache key for identifying cached section data."""

    surface_id: ScheduledSurfaceId


@dataclass
class CacheEntry:
    """Class to store cached section data."""

    sections: list[CorpusSection]
    expiration: datetime
    lock: asyncio.Lock


class SectionsCorpusBackend(SectionsCorpusProtocol):
    """Backend for fetching corpus sections using the getSections query."""

    http_client: AsyncClient
    graph_config: CorpusApiGraphConfig
    metrics_client: aiodogstatsd.Client
    manifest_provider: ManifestProvider

    cache_time_to_live_min = timedelta(seconds=50)
    cache_time_to_live_max = timedelta(seconds=70)
    _cache: dict[CacheKey, CacheEntry]
    _background_tasks: set[asyncio.Task]

    def __init__(
        self,
        http_client: AsyncClient,
        graph_config: CorpusApiGraphConfig,
        metrics_client: aiodogstatsd.Client,
        manifest_provider: ManifestProvider,
    ) -> None:
        """Initialize the SectionsCorpusBackend."""
        self.http_client = http_client
        self.graph_config = graph_config
        self.metrics_client = metrics_client
        self.manifest_provider = manifest_provider
        self._cache = {}
        self._background_tasks = set()

    async def fetch(self, surface_id: ScheduledSurfaceId) -> list[CorpusSection]:
        """Fetch section recommendations using caching and request coalescing."""
        cache_key = CacheKey(surface_id)
        if cache_key in self._cache:
            cache_entry = self._cache[cache_key]
            if datetime.now() >= cache_entry.expiration:
                task = asyncio.create_task(self._revalidate_cache(surface_id))
                self._background_tasks.add(task)
                task.add_done_callback(self._background_tasks.discard)
            return cache_entry.sections

        return await self._revalidate_cache(surface_id)

    async def _revalidate_cache(self, surface_id: ScheduledSurfaceId) -> list[CorpusSection]:
        """Update the cache for a specific surface and return section recommendations."""
        cache_key = CacheKey(surface_id)
        if cache_key not in self._cache:
            self._cache[cache_key] = CacheEntry([], datetime.min, asyncio.Lock())

        async with self._cache[cache_key].lock:
            if datetime.now() < self._cache[cache_key].expiration:
                return self._cache[cache_key].sections
            try:
                sections = await self._fetch_from_backend(surface_id)
                self._cache[cache_key] = CacheEntry(
                    sections,
                    get_expiration_time(self.cache_time_to_live_min, self.cache_time_to_live_max),
                    asyncio.Lock(),
                )
                return sections
            except Exception as e:
                if self._cache[cache_key].sections:
                    logger.error(
                        f"Failed to update sections cache: {e}. Returning stale cached data."
                    )
                    return self._cache[cache_key].sections
                else:
                    raise

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
    async def _fetch_from_backend(self, surface_id: ScheduledSurfaceId) -> list[CorpusSection]:
        """Issue a getSections query to fetch section recommendations from the backend."""
        query = """
            query GetSections($filters: SectionFilters!) {
              getSections(filters: $filters) {
                externalId
                active
                title
                sectionItems {
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
        variables = {"filters": {"scheduledSurfaceGuid": surface_id}}
        with self.metrics_client.timeit("corpus_api.get_sections.timing"):
            res = await self.http_client.post(
                self.graph_config.endpoint,
                json={"query": query, "variables": variables},
                headers=self.graph_config.headers,
            )

        # Error handling for HTTP and GraphQL errors
        self.metrics_client.increment(f"corpus_api.get_sections.status_codes.{res.status_code}")
        res.raise_for_status()
        data = res.json()
        if "errors" in data:
            self.metrics_client.increment("corpus_api.get_sections.graphql_error")
            raise CorpusGraphQLError(f"Sections API returned GraphQL errors {data['errors']}")

        utm_source = get_utm_source(surface_id)
        sections_list = []
        for section in data["data"]["getSections"]:
            if not section.get("active"):
                logger.info(f"Skipping inactive section {section['externalId']} for {surface_id}")
                continue

            section = CorpusSection(
                externalId=section["externalId"],
                title=section["title"],
                sectionItems=[
                    build_corpus_item(
                        section_item["corpusItem"], self.manifest_provider, utm_source
                    )
                    for section_item in section["sectionItems"]
                ],
            )
            sections_list.append(section)

        return sections_list
