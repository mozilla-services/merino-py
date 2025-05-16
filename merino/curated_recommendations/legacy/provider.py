"""Provider for curated recommendations on legacy Firefox versions(114, 115-129) New Tab."""

from pydantic import HttpUrl
from urllib.parse import quote
from merino.curated_recommendations.corpus_backends.scheduled_surface_backend import (
    ScheduledSurfaceProtocol,
)
from merino.curated_recommendations.utils import (
    get_recommendation_surface_id,
)
from merino.curated_recommendations.protocol import CuratedRecommendation
from merino.curated_recommendations.legacy.protocol import (
    CuratedRecommendationLegacyFx115Fx129,
    CuratedRecommendationLegacyFx114,
    CuratedRecommendationsLegacyFx115Fx129Request,
    CuratedRecommendationsLegacyFx115Fx129Response,
    CuratedRecommendationsLegacyFx114Request,
    CuratedRecommendationsLegacyFx114Response,
)


class LegacyCuratedRecommendationsProvider:
    """Provider for curated recommendations for legacy Firefox versions.
    Provides separate recommendations for v114 and for v115-129
    """

    scheduled_surface_backend: ScheduledSurfaceProtocol

    def __init__(
        self,
        scheduled_surface_backend: ScheduledSurfaceProtocol,
    ) -> None:
        self.scheduled_surface_backend = scheduled_surface_backend

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
        self, request: CuratedRecommendationsLegacyFx115Fx129Request
    ) -> CuratedRecommendationsLegacyFx115Fx129Response:
        """Provide curated recommendations for /curated-recommendations/legacy-115-129 endpoint."""
        surface_id = get_recommendation_surface_id(locale=request.locale, region=request.region)

        corpus_items = await self.scheduled_surface_backend.fetch(surface_id)
        base_recommendations = [
            CuratedRecommendation(
                **item.model_dump(),
                receivedRank=rank,
                # Use the topic as a weight-1.0 feature so the client can aggregate a coarse
                # interest vector. Data science work shows that using the topics as features
                # is effective as a first pass at personalization.
                # https://mozilla-hub.atlassian.net/wiki/x/FoV5Ww
                features={item.topic.value: 1.0} if item.topic else {},
            )
            for rank, item in enumerate(corpus_items)
        ]

        legacy_recommendations = (
            self.map_curated_recommendations_to_legacy_recommendations_fx_115_129(
                base_recommendations
            )
        )

        # build response for api request
        return CuratedRecommendationsLegacyFx115Fx129Response(
            data=legacy_recommendations[: request.count],
        )

    async def fetch_recommendations_for_legacy_fx_114(
        self, request: CuratedRecommendationsLegacyFx114Request
    ) -> CuratedRecommendationsLegacyFx114Response:
        """Provide curated recommendations for /curated-recommendations/legacy-115-129 endpoint."""
        surface_id = get_recommendation_surface_id(
            locale=request.locale_lang, region=request.region
        )

        corpus_items = await self.scheduled_surface_backend.fetch(surface_id)
        base_recommendations = [
            CuratedRecommendation(
                **item.model_dump(),
                receivedRank=rank,
                # Use the topic as a weight-1.0 feature so the client can aggregate a coarse
                # interest vector. Data science work shows that using the topics as features
                # is effective as a first pass at personalization.
                # https://mozilla-hub.atlassian.net/wiki/x/FoV5Ww
                features={item.topic.value: 1.0} if item.topic else {},
            )
            for rank, item in enumerate(corpus_items)
        ]

        legacy_global_recommendations = (
            self.map_curated_recommendations_to_legacy_recommendations_fx_114(base_recommendations)
        )

        # build response for api request
        return CuratedRecommendationsLegacyFx114Response(
            recommendations=legacy_global_recommendations[: request.count],
        )
