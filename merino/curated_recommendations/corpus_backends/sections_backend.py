"""Corpus Sections API backend for fetching section recommendations using the getSections GraphQL query."""

import asyncio
import logging
from datetime import timedelta

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
    SectionsProtocol,
    CorpusSection,
    SurfaceId,
)
from merino.curated_recommendations.corpus_backends.utils import (
    get_utm_source,
    build_corpus_item,
    CorpusGraphQLError,
    CorpusApiGraphConfig,
)
from merino.providers.manifest import Provider as ManifestProvider

logger = logging.getLogger(__name__)


class SectionsBackend(SectionsProtocol):
    """Backend for fetching corpus sections using the getSections query."""

    http_client: AsyncClient
    graph_config: CorpusApiGraphConfig
    metrics_client: aiodogstatsd.Client
    manifest_provider: ManifestProvider

    _cache: dict
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

    @stale_while_revalidate(
        wait_expiration=WaitRandomExpiration(timedelta(seconds=50), timedelta(seconds=70)),
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
    async def fetch(self, surface_id: SurfaceId) -> list[CorpusSection]:
        """Fetch section recommendations from the backend."""
        query = """
            query GetSections($filters: SectionFilters!) {
              getSections(filters: $filters) {
                externalId
                active
                title
                iab {
                    taxonomy
                    categories
                }
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

            section_obj = CorpusSection(
                externalId=section["externalId"],
                title=section["title"],
                iab=section.get("iab"),  # Handle optional IAB data
                sectionItems=[
                    build_corpus_item(
                        section_item["corpusItem"], self.manifest_provider, utm_source
                    )
                    for section_item in section["sectionItems"]
                ],
            )
            sections_list.append(section_obj)

        return sections_list
