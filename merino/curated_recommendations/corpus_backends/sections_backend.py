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


def parse_section_external_id(raw_external_id: str) -> tuple[str, int]:
    """Normalize a raw section ID into its canonical ID and experiment variant."""
    # Strip any locale suffix (e.g., "__lEN_GB", "__lEN_CA") from externalId if present.
    external_id = raw_external_id.split("__l", 1)[0]

    marker = "__exp"
    idx = external_id.rfind(marker)
    if idx <= 0:
        return external_id.split("__", 1)[0], 0

    base_id = external_id[:idx]
    variant_id = external_id[idx + len(marker) :]
    if variant_id.isdigit():
        return base_id, int(variant_id)

    return external_id.split("__", 1)[0], 0


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
        """Fetch section recommendations from the backend.

        Experimental sections are omitted from the top-level result and linked
        to their canonical base sections for downstream resolution.
        """
        query = """
            query GetSections($filters: SectionFilters!) {
              getSections(filters: $filters) {
                createSource
                externalId
                active
                title
                description
                heroTitle
                heroDescription
                followable
                allowAds
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
        parsed_sections = []
        for section in data["data"]["getSections"]:
            if not section.get("active") or section.get("externalId", "").endswith("_crawl"):
                logger.info(f"Skipping inactive section {section['externalId']} for {surface_id}")
                continue

            external_id, experiment_variant = parse_section_external_id(section["externalId"])

            section_obj = CorpusSection(
                externalId=external_id,
                title=section["title"],
                description=section.get("description"),  # use .get (can be None)
                heroTitle=section.get("heroTitle"),
                heroSubtitle=section.get("heroDescription"),
                iab=section["iab"],
                createSource=section["createSource"],
                experimentVariant=experiment_variant,
                followable=section["followable"],
                allowAds=section["allowAds"],
                sectionItems=[
                    build_corpus_item(
                        section_item["corpusItem"], self.manifest_provider, utm_source
                    )
                    for section_item in section["sectionItems"]
                ],
            )
            parsed_sections.append(section_obj)

        base_sections = [s for s in parsed_sections if s.experimentVariant == 0]
        experimental_sections = [s for s in parsed_sections if s.experimentVariant != 0]

        base_sections_by_id: dict[str, CorpusSection] = {s.externalId: s for s in base_sections}

        for section in experimental_sections:
            base = base_sections_by_id.get(section.externalId)
            if base and base.alternateSection is None:
                base.alternateSection = section

        sections_list = base_sections

        return sections_list
