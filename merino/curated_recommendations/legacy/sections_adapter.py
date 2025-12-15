"""Adapter for converting sections data to legacy flat list format."""

import logging

from merino.curated_recommendations.corpus_backends.protocol import (
    SectionsProtocol,
    SurfaceId,
    Topic,
)
from merino.curated_recommendations.engagement_backends.protocol import EngagementBackend
from merino.curated_recommendations.prior_backends.protocol import PriorBackend
from merino.curated_recommendations.protocol import CuratedRecommendation
from merino.curated_recommendations.sections import get_corpus_sections_for_legacy_topic
from merino.curated_recommendations.rankers import (
    takedown_reported_recommendations,
    ThompsonSamplingRanker,
    spread_publishers,
    boost_preferred_topic,
    renumber_recommendations,
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
    ranker = ThompsonSamplingRanker(
        engagement_backend=engagement_backend,
        prior_backend=prior_backend,
    )
    recommendations = ranker.rank_items(recommendations, region=region, rescaler=None)

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
