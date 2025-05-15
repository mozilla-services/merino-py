"""Provider for curated recommendations on New Tab."""

import logging
from typing import cast

from merino.curated_recommendations.corpus_backends.protocol import (
    ScheduledSurfaceProtocol,
    SurfaceId,
    SectionsProtocol,
    Topic,
)
from merino.curated_recommendations.engagement_backends.protocol import EngagementBackend
from merino.curated_recommendations.interest_picker import create_interest_picker
from merino.curated_recommendations.localization import LOCALIZED_SECTION_TITLES
from merino.curated_recommendations.prior_backends.protocol import PriorBackend
from merino.curated_recommendations.protocol import (
    CuratedRecommendation,
    CuratedRecommendationsRequest,
    CuratedRecommendationsDesktopV1Request,
    CuratedRecommendationsResponse,
)
from merino.curated_recommendations.rankers import (
    boost_preferred_topic,
    spread_publishers,
    thompson_sampling,
)
from merino.curated_recommendations.sections import get_sections
from merino.curated_recommendations.utils import (
    get_recommendation_surface_id,
    get_millisecond_epoch_time,
    derive_region,
)

logger = logging.getLogger(__name__)


class CuratedRecommendationsProvider:
    """Provider for recommendations that have been reviewed by human curators."""

    scheduled_surface_backend: ScheduledSurfaceProtocol
    sections_backend: SectionsProtocol

    def __init__(
        self,
        scheduled_surface_backend: ScheduledSurfaceProtocol,
        engagement_backend: EngagementBackend,
        prior_backend: PriorBackend,
        sections_backend: SectionsProtocol,
    ) -> None:
        self.scheduled_surface_backend = scheduled_surface_backend
        self.engagement_backend = engagement_backend
        self.prior_backend = prior_backend
        self.sections_backend = sections_backend

    @staticmethod
    def is_sections_experiment(
        request: CuratedRecommendationsRequest,
        surface_id: SurfaceId,
    ) -> bool:
        """Check if the 'sections' experiment is enabled."""
        return (
            request.feeds is not None
            and "sections" in request.feeds  # Clients must request "feeds": ["sections"]
            and surface_id in LOCALIZED_SECTION_TITLES  # The locale must be supported
        )

    def rank_recommendations(
        self,
        recommendations: list[CuratedRecommendation],
        request: CuratedRecommendationsRequest,
    ) -> list[CuratedRecommendation]:
        """Apply additional processing to the list of recommendations
        received from Curated Corpus API

        @param recommendations: A list of CuratedRecommendation objects as they are received
        from Curated Corpus API
        @param surface_id: a string identifier for the New Tab surface these recommendations
        are intended for
        @param request: The full API request with all the data
        @return: A re-ranked list of curated recommendations
        """
        # 3. Apply Thompson sampling to rank recommendations by engagement
        recommendations = thompson_sampling(
            recommendations,
            engagement_backend=self.engagement_backend,
            prior_backend=self.prior_backend,
            region=derive_region(request.locale, request.region),
        )

        # 2. Perform publisher spread on the recommendation set
        recommendations = spread_publishers(recommendations, spread_distance=3)

        # 1. Finally, perform preferred topics boosting if preferred topics are passed in the request
        if request.topics:
            validated_topics: list[Topic] = cast(list[Topic], request.topics)
            recommendations = boost_preferred_topic(recommendations, validated_topics)

        # 0. Blast-off!
        for rank, rec in enumerate(recommendations):
            # Update received_rank now that recommendations have been ranked.
            rec.receivedRank = rank

        return recommendations[: request.count]

    async def fetch(
        self, request: CuratedRecommendationsRequest
    ) -> CuratedRecommendationsResponse:
        """Provide curated recommendations."""
        surface_id = get_recommendation_surface_id(locale=request.locale, region=request.region)

        corpus_items = await self.scheduled_surface_backend.fetch(surface_id)
        recommendations = [
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

        sections_feeds = None
        general_feed = []
        if self.is_sections_experiment(request, surface_id):
            sections_feeds = await get_sections(
                recommendations,
                request,
                surface_id,
                engagement_backend=self.engagement_backend,
                prior_backend=self.prior_backend,
                sections_backend=self.sections_backend,
            )
        else:
            general_feed = self.rank_recommendations(recommendations, request)

        response = CuratedRecommendationsResponse(
            recommendedAt=get_millisecond_epoch_time(),
            surfaceId=surface_id,
            data=general_feed,
            feeds=sections_feeds,
        )

        if request.enableInterestPicker and response.feeds:
            response.interestPicker = create_interest_picker(response.feeds)

        return response

    async def fetch_recommendations_for_desktop_v1(
        self, request: CuratedRecommendationsDesktopV1Request
    ) -> list[CuratedRecommendation]:
        """Provide curated recommendations."""
        surface_id = get_recommendation_surface_id(locale=request.locale, region=request.region)

        corpus_items = await self.scheduled_surface_backend.fetch(surface_id)
        recommendations = [
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
        return recommendations
