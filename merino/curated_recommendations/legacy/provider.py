"""Provider for curated recommendations on legacy Firefox versions(114, 115-129) New Tab."""

from pydantic import HttpUrl
from urllib.parse import quote

from merino.curated_recommendations.provider import CuratedRecommendationsProvider
from merino.curated_recommendations.protocol import (
    CuratedRecommendation,
    CuratedRecommendationsRequest,
    Locale,
)
from merino.curated_recommendations.legacy.protocol import (
    CuratedRecommendationLegacyFx115Fx129,
    CuratedRecommendationLegacyFx114,
    CuratedRecommendationsLegacyFx115Fx129Request,
    CuratedRecommendationsLegacyFx115Fx129Response,
    CuratedRecommendationsLegacyFx114Request,
    CuratedRecommendationsLegacyFx114Response,
)
from merino.curated_recommendations.corpus_backends.protocol import SurfaceId
from merino.curated_recommendations.legacy.sections_adapter import (
    get_legacy_recommendations_from_sections,
)
from merino.curated_recommendations.prior_backends.engagment_rescaler import (
    CrawledContentRescaler,
    UKCrawledContentRescaler,
)
from merino.curated_recommendations.utils import (
    get_recommendation_surface_id,
    derive_region,
)

DEFAULT_RECOMMENDATION_COUNT = 30


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

    @staticmethod
    async def _get_base_recommendations(
        locale: Locale,
        region: str | None,
        count: int | None,
        curated_corpus_provider: CuratedRecommendationsProvider,
    ) -> list[CuratedRecommendation]:
        """Fetch base recommendations from sections backend (US/GB) or scheduler (other)."""
        surface_id = get_recommendation_surface_id(locale, region)

        if surface_id in (SurfaceId.NEW_TAB_EN_US, SurfaceId.NEW_TAB_EN_GB):
            # US/GB: fetch from sections backend instead of scheduler
            rescaler = (
                UKCrawledContentRescaler()
                if surface_id == SurfaceId.NEW_TAB_EN_GB
                else CrawledContentRescaler()
            )
            return await get_legacy_recommendations_from_sections(
                sections_backend=curated_corpus_provider.sections_backend,
                engagement_backend=curated_corpus_provider.engagement_backend,
                prior_backend=curated_corpus_provider.prior_backend,
                surface_id=surface_id,
                count=count or DEFAULT_RECOMMENDATION_COUNT,
                region=derive_region(locale, region),
                rescaler=rescaler,
            )

        # Other locales: use scheduler via curated recommendations provider
        request = CuratedRecommendationsRequest(locale=locale, region=region, count=count)
        return (await curated_corpus_provider.fetch(request)).data

    async def fetch_recommendations_for_legacy_fx_115_129(
        self,
        request: CuratedRecommendationsLegacyFx115Fx129Request,
        curated_corpus_provider: CuratedRecommendationsProvider,
    ) -> CuratedRecommendationsLegacyFx115Fx129Response:
        """Provide curated recommendations for /curated-recommendations/legacy-115-129 endpoint."""
        base_recommendations = await self._get_base_recommendations(
            locale=request.locale,
            region=request.region,
            count=request.count,
            curated_corpus_provider=curated_corpus_provider,
        )
        legacy_recommendations = (
            self.map_curated_recommendations_to_legacy_recommendations_fx_115_129(
                base_recommendations
            )
        )
        return CuratedRecommendationsLegacyFx115Fx129Response(data=legacy_recommendations)

    async def fetch_recommendations_for_legacy_fx_114(
        self,
        request: CuratedRecommendationsLegacyFx114Request,
        curated_corpus_provider: CuratedRecommendationsProvider,
    ) -> CuratedRecommendationsLegacyFx114Response:
        """Provide curated recommendations for /curated-recommendations/legacy-114 endpoint."""
        base_recommendations = await self._get_base_recommendations(
            locale=request.locale_lang,
            region=request.region,
            count=request.count,
            curated_corpus_provider=curated_corpus_provider,
        )
        legacy_recommendations = self.map_curated_recommendations_to_legacy_recommendations_fx_114(
            base_recommendations
        )
        return CuratedRecommendationsLegacyFx114Response(
            recommendations=legacy_recommendations,
        )
