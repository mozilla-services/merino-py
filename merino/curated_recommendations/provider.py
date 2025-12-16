"""Provider for curated recommendations on New Tab."""

import logging
from typing import cast

from merino.curated_recommendations import LocalModelBackend, MLRecsBackend
from merino.curated_recommendations.ml_backends.protocol import LOCAL_MODEL_MODEL_ID_KEY
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
    CuratedRecommendationsResponse,
    ProcessedInterests,
)

from merino.curated_recommendations.rankers import (
    boost_preferred_topic,
    spread_publishers,
    ThompsonSamplingRanker,
)
from merino.curated_recommendations.sections import get_sections
from merino.curated_recommendations.utils import (
    get_recommendation_surface_id,
    get_millisecond_epoch_time,
    derive_region,
)

logger = logging.getLogger(__name__)

LOCAL_MODEL_DB_VALUES_KEY = "values"  # Key to differentially private values


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
        local_model_backend: LocalModelBackend,
        ml_recommendations_backend: MLRecsBackend,
    ) -> None:
        self.scheduled_surface_backend = scheduled_surface_backend
        self.engagement_backend = engagement_backend
        self.prior_backend = prior_backend
        self.sections_backend = sections_backend
        self.local_model_backend = local_model_backend
        self.ml_recommendations_backend = ml_recommendations_backend

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
        ranker = ThompsonSamplingRanker(
            engagement_backend=self.engagement_backend, prior_backend=self.prior_backend
        )
        recommendations = ranker.rank_items(
            recommendations,
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

        sections_feeds = None
        general_feed: list[CuratedRecommendation] = []

        if self.is_sections_experiment(request, surface_id):
            inferred_interests = self.process_request_interests(
                request, surface_id, self.local_model_backend
            )
            sections_feeds = await get_sections(
                request,
                surface_id,
                engagement_backend=self.engagement_backend,
                personal_interests=inferred_interests,
                prior_backend=self.prior_backend,
                sections_backend=self.sections_backend,
                ml_backend=self.ml_recommendations_backend,
                scheduled_surface_backend=self.scheduled_surface_backend,
                region=derive_region(request.locale, request.region),
            )
        elif surface_id == SurfaceId.NEW_TAB_EN_US:
            # US non-sections: fetch from sections backend instead of scheduler
            from merino.curated_recommendations.legacy.sections_adapter import (
                get_legacy_recommendations_from_sections,
            )

            general_feed = await get_legacy_recommendations_from_sections(
                sections_backend=self.sections_backend,
                engagement_backend=self.engagement_backend,
                prior_backend=self.prior_backend,
                surface_id=surface_id,
                count=request.count,
                region=derive_region(request.locale, request.region),
                topics=cast(list[Topic], request.topics) if request.topics else None,
            )
        else:
            # Non-US/CA markets: fetch from scheduled surface backend
            corpus_items = await self.scheduled_surface_backend.fetch(surface_id)
            recommendations = [
                CuratedRecommendation(
                    **item.model_dump(),
                    receivedRank=rank,
                    # Use the topic as a weight-1.0 feature so the client can aggregate a coarse
                    # interest vector. Data science work shows that using the topics as features
                    # is effective as a first pass at personalization.
                    # https://mozilla-hub.atlassian.net/wiki/x/FoV5Ww
                    features={f"t_{item.topic.value}": 1.0} if item.topic else {},
                )
                for rank, item in enumerate(corpus_items)
            ]
            general_feed = self.rank_recommendations(recommendations, request)
        response = CuratedRecommendationsResponse(
            recommendedAt=get_millisecond_epoch_time(),
            surfaceId=surface_id,
            data=general_feed,
            feeds=sections_feeds,
            inferredLocalModel=self.local_model_backend.get(
                surface_id,
                experiment_name=request.experimentName,
                experiment_branch=request.experimentBranch,
            )
            if request.inferredInterests
            else None,  # Inferred interests being not none implies personalization
        )

        if request.enableInterestPicker and response.feeds:
            response.interestPicker = create_interest_picker(response.feeds)

        return response

    @staticmethod
    def process_request_interests(
        request: CuratedRecommendationsRequest,
        surface_id: str,
        local_model_backend: LocalModelBackend,
    ) -> ProcessedInterests | None:
        """Convert the interest vector from the request into a clean internal representation
        with numeric scores. This does the unary decoding if necessary.

        Older models may be supported in some instances, otherwise scores will be empty.
        """
        request_interests = request.inferredInterests
        if request_interests is None:
            return None

        # Extract model_id if present
        model_id = request_interests.get_model_used()
        if model_id is None:
            return None
        scores = {}
        # We need a known model ID in the request to interpret the values sent.
        inferred_local_model = local_model_backend.get(
            model_id=model_id,
            surface_id=surface_id,
            experiment_name=request.experimentName,
            experiment_branch=request.experimentBranch,
        )
        # TODO - pass through computed surface ID

        # Check if we need to decode differentially private values
        if inferred_local_model is not None and inferred_local_model.model_matches_interests(
            model_id
        ):
            dp_values: list[str] | None = cast(
                list[str] | None, request_interests.root.get(LOCAL_MODEL_DB_VALUES_KEY)
            )
            if dp_values is not None:
                # Decode the DP values
                decoded = inferred_local_model.decode_dp_interests(dp_values, model_id)
                # Extract just the numeric scores
                scores = {
                    k: v
                    for k, v in decoded.items()
                    if k != LOCAL_MODEL_MODEL_ID_KEY and isinstance(v, (int, float))
                }
                return ProcessedInterests(
                    model_id=model_id,
                    scores=scores,
                    expected_keys=inferred_local_model.get_interest_keys(),
                )

        # Either no decoding needed or no model available - extract existing scores
        for key, value in request_interests.root.items():
            if key not in ["model_id", LOCAL_MODEL_DB_VALUES_KEY] and isinstance(
                value, (int, float)
            ):
                scores[key] = float(value)
        return ProcessedInterests(model_id=model_id, scores=scores)
