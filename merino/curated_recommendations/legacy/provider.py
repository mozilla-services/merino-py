"""Provider for curated recommendations on legacy Firefox versions(114, 115-129) New Tab."""

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
        # build a CuratedRecommendationsRequest object for the `fetch` method
        # of curated recommendations provider from the request query params
        curated_rec_req_from_legacy_req = CuratedRecommendationsRequest(
            locale=request.locale, region=request.region
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

        # build the endpoint response with the length of `count` request query param
        return CuratedRecommendationsLegacyFx115Fx129Response(
            data=legacy_recommendations[: request.count],
        )

    async def fetch_recommendations_for_legacy_fx_114(
        self,
        request: CuratedRecommendationsLegacyFx114Request,
        curated_corpus_provider: CuratedRecommendationsProvider,
    ) -> CuratedRecommendationsLegacyFx114Response:
        """Provide curated recommendations for /curated-recommendations/legacy-115-129 endpoint."""
        # build a CuratedRecommendationsRequest object for the `fetch` method
        # of curated recommendations provider from the request query params
        curated_rec_req_from_legacy_req = CuratedRecommendationsRequest(
            locale=request.locale_lang, region=request.region
        )

        # get base recs from the curated recommendations provider
        base_recommendations = (
            await curated_corpus_provider.fetch(curated_rec_req_from_legacy_req)
        ).data

        # map base recommendations to fx 114 recommendations
        legacy_global_recommendations = (
            self.map_curated_recommendations_to_legacy_recommendations_fx_114(base_recommendations)
        )

        # build the endpoint response with the length of `count` request query param
        return CuratedRecommendationsLegacyFx114Response(
            recommendations=legacy_global_recommendations[: request.count],
        )
