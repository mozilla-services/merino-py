"""Provider for curated recommendations on legacy Firefox versions(114, 115-129) New Tab."""

import logging
from pydantic import HttpUrl
from urllib.parse import quote

from merino.curated_recommendations.provider import CuratedRecommendationsProvider
from merino.curated_recommendations.protocol import (
    CuratedRecommendation,
    CuratedRecommendationsRequest,
)
from merino.curated_recommendations.legacy.protocol import (
    CuratedRecommendationLegacyFx115Fx129,
    CuratedRecommendationLegacyFx114,
    CuratedRecommendationsLegacyFx115Fx129Request,
    CuratedRecommendationsLegacyFx115Fx129Response,
    CuratedRecommendationsLegacyFx114Request,
    CuratedRecommendationsLegacyFx114Response,
)
from merino.curated_recommendations.corpus_backends.protocol import (
    SectionsProtocol,
    SurfaceId,
    Topic,
)
from merino.curated_recommendations.engagement_backends.protocol import EngagementBackend
from merino.curated_recommendations.prior_backends.protocol import PriorBackend
from merino.curated_recommendations.sections import get_corpus_sections_for_legacy_topic
from merino.curated_recommendations.rankers import (
    takedown_reported_recommendations,
    thompson_sampling,
    spread_publishers,
    boost_preferred_topic,
    renumber_recommendations,
)
from merino.curated_recommendations.utils import (
    get_recommendation_surface_id,
    derive_region,
)

logger = logging.getLogger(__name__)


async def get_legacy_recommendations_from_sections(
    sections_backend: SectionsProtocol,
    engagement_backend: EngagementBackend,
    prior_backend: PriorBackend,
    surface_id: SurfaceId,
    count: int,
    region: str | None = None,
    topics: list[Topic] | None = None,
) -> list[CuratedRecommendation]:
    """Fetch section items for NEW_TAB_EN_US and return as flat list.

    Args:
        sections_backend: Backend to fetch corpus sections
        engagement_backend: Backend for engagement data (Thompson sampling)
        prior_backend: Backend for priors (Thompson sampling)
        surface_id: Surface identifier (should be NEW_TAB_EN_US)
        count: Maximum number of recommendations to return
        region: Optional region for engagement filtering (e.g., 'US', 'CA')
        topics: Optional list of preferred topics for boosting

    Returns:
        Ranked list of CuratedRecommendation objects
    """
    from merino.curated_recommendations.sections import get_corpus_sections

    # 1. Fetch sections from sections_backend
    headlines_section, corpus_sections = await get_corpus_sections(
        sections_backend=sections_backend,
        surface_id=surface_id,
        min_feed_rank=0,
        include_subtopics=False,
        scheduled_surface_backend=None,
    )

    # 2. Filter to legacy topics
    legacy_sections = get_corpus_sections_for_legacy_topic(corpus_sections)

    # 3. Extract all recommendations from legacy sections, deduplicating by corpusItemId
    seen_ids: set[str] = set()
    recommendations: list[CuratedRecommendation] = []

    for section in legacy_sections.values():
        for rec in section.recommendations:
            if rec.corpusItemId in seen_ids:
                continue
            seen_ids.add(rec.corpusItemId)
            # 4. Set scheduledCorpusItemId = corpusItemId for each item (also generates tileId)
            rec.update_scheduled_corpus_item_id(rec.corpusItemId)
            recommendations.append(rec)

    # 5. Filter reported content
    recommendations = takedown_reported_recommendations(
        recommendations,
        engagement_backend=engagement_backend,
        region=region,
    )

    # 6. Apply Thompson sampling (with rescaler=None)
    recommendations = thompson_sampling(
        recommendations,
        engagement_backend=engagement_backend,
        prior_backend=prior_backend,
        region=region,
        rescaler=None,
    )

    # 7. Apply publisher spread
    recommendations = spread_publishers(recommendations, spread_distance=3)

    # 8. Apply topic boost if topics provided
    if topics:
        recommendations = boost_preferred_topic(recommendations, topics)

    # 9. Renumber receivedRank sequentially
    renumber_recommendations(recommendations)

    # 10. Limit to count items
    recommendations = recommendations[:count]

    # 11. If no recommendations after filtering, log error and return empty list
    if not recommendations:
        logger.error(
            f"No recommendations available after filtering for surface_id={surface_id}, region={region}"
        )

    return recommendations


class LegacyCuratedRecommendationsProvider:
    """Provider for curated recommendations for legacy Firefox versions.
    Provides separate recommendations for v114 and for v115-129
    """

    @staticmethod
    def transform_image_url_to_pocket_cdn(original_url: HttpUrl) -> HttpUrl:
        """Transform an original image URL to a Pocket CDN URL for the given image with a fixed width of 450px.

        The original URL is encoded and embedded as a query parameter.
        """
        encoded_url = quote(str(original_url), safe="")
        return HttpUrl(
            f"https://img-getpocket.cdn.mozilla.net/direct?url={encoded_url}&resize=w450"
        )

    @staticmethod
    def map_curated_recommendations_to_legacy_recommendations_fx_115_129(
        base_recommendations: list[CuratedRecommendation],
    ) -> list[CuratedRecommendationLegacyFx115Fx129]:
        """Map CuratedRecommendation object to CuratedRecommendationLegacyFx115Fx129"""
        return [
            CuratedRecommendationLegacyFx115Fx129(
                typename="Recommendation",
                recommendationId=item.corpusItemId,
                tileId=item.tileId,
                url=item.url,
                title=item.title,
                excerpt=item.excerpt,
                publisher=item.publisher,
                imageUrl=item.imageUrl,
            )
            for item in base_recommendations
        ]

    @staticmethod
    def map_curated_recommendations_to_legacy_recommendations_fx_114(
        base_recommendations: list[CuratedRecommendation],
    ) -> list[CuratedRecommendationLegacyFx114]:
        """Map CuratedRecommendation object to CuratedRecommendationLegacyFx114"""
        return [
            CuratedRecommendationLegacyFx114(
                id=item.tileId,
                title=item.title,
                url=item.url,
                excerpt=item.excerpt,
                domain=item.publisher,
                image_src=LegacyCuratedRecommendationsProvider.transform_image_url_to_pocket_cdn(
                    item.imageUrl
                ),
                raw_image_src=item.imageUrl,
            )
            for item in base_recommendations
        ]

    async def fetch_recommendations_for_legacy_fx_115_129(
        self,
        request: CuratedRecommendationsLegacyFx115Fx129Request,
        curated_corpus_provider: CuratedRecommendationsProvider,
    ) -> CuratedRecommendationsLegacyFx115Fx129Response:
        """Provide curated recommendations for /curated-recommendations/legacy-115-129 endpoint."""
        surface_id = get_recommendation_surface_id(request.locale, request.region)

        if surface_id == SurfaceId.NEW_TAB_EN_US:
            # NEW: Use sections
            base_recommendations = await get_legacy_recommendations_from_sections(
                sections_backend=curated_corpus_provider.sections_backend,
                engagement_backend=curated_corpus_provider.engagement_backend,
                prior_backend=curated_corpus_provider.prior_backend,
                surface_id=surface_id,
                count=request.count,
                region=derive_region(request.locale, request.region),
            )
        else:
            # Existing path for non-US/CA
            curated_rec_req_from_legacy_req = CuratedRecommendationsRequest(
                locale=request.locale, region=request.region, count=request.count
            )

            # get base recs from the curated recommendations provider
            base_recommendations = (
                await curated_corpus_provider.fetch(curated_rec_req_from_legacy_req)
            ).data

        # map base recommendations to fx 115-129 recommendations
        legacy_recommendations = (
            self.map_curated_recommendations_to_legacy_recommendations_fx_115_129(
                base_recommendations
            )
        )

        # build the endpoint response
        return CuratedRecommendationsLegacyFx115Fx129Response(data=legacy_recommendations)

    async def fetch_recommendations_for_legacy_fx_114(
        self,
        request: CuratedRecommendationsLegacyFx114Request,
        curated_corpus_provider: CuratedRecommendationsProvider,
    ) -> CuratedRecommendationsLegacyFx114Response:
        """Provide curated recommendations for /curated-recommendations/legacy-115-129 endpoint."""
        surface_id = get_recommendation_surface_id(request.locale_lang, request.region)

        if surface_id == SurfaceId.NEW_TAB_EN_US:
            # NEW: Use sections
            base_recommendations = await get_legacy_recommendations_from_sections(
                sections_backend=curated_corpus_provider.sections_backend,
                engagement_backend=curated_corpus_provider.engagement_backend,
                prior_backend=curated_corpus_provider.prior_backend,
                surface_id=surface_id,
                count=request.count,
                region=derive_region(request.locale_lang, request.region),
            )
        else:
            # Existing path for non-US/CA
            curated_rec_req_from_legacy_req = CuratedRecommendationsRequest(
                locale=request.locale_lang, region=request.region, count=request.count
            )

            # get base recs from the curated recommendations provider
            base_recommendations = (
                await curated_corpus_provider.fetch(curated_rec_req_from_legacy_req)
            ).data

        # map base recommendations to fx 114 recommendations
        legacy_global_recommendations = (
            self.map_curated_recommendations_to_legacy_recommendations_fx_114(base_recommendations)
        )

        # build the endpoint response
        return CuratedRecommendationsLegacyFx114Response(
            recommendations=legacy_global_recommendations,
        )
