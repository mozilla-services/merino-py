"""Adapter for converting sections data to legacy flat list format."""

import logging

from merino.curated_recommendations.corpus_backends.protocol import (
    SectionsProtocol,
    SurfaceId,
)
from merino.curated_recommendations.engagement_backends.protocol import EngagementBackend
from merino.curated_recommendations.prior_backends.protocol import PriorBackend
from merino.curated_recommendations.protocol import CuratedRecommendation, Section
from merino.curated_recommendations.sections import (
    get_corpus_sections,
    get_corpus_sections_for_legacy_topic,
)
from merino.curated_recommendations.rankers import (
    takedown_reported_recommendations,
    ThompsonSamplingRanker,
    spread_publishers,
    renumber_recommendations,
)

logger = logging.getLogger(__name__)


def extract_recommendations_from_sections(
    sections: dict[str, Section],
) -> list[CuratedRecommendation]:
    """Extract and deduplicate recommendations from sections.

    Args:
        sections: Dict mapping section IDs to Section objects

    Returns:
        Deduplicated list of recommendations with scheduledCorpusItemId set
    """
    seen_ids: set[str] = set()
    recommendations: list[CuratedRecommendation] = []

    for section in sections.values():
        for rec in section.recommendations:
            if rec.corpusItemId in seen_ids:
                continue
            seen_ids.add(rec.corpusItemId)
            rec.update_scheduled_corpus_item_id(rec.corpusItemId)
            recommendations.append(rec)

    return recommendations


async def get_legacy_recommendations_from_sections(
    sections_backend: SectionsProtocol,
    engagement_backend: EngagementBackend,
    prior_backend: PriorBackend,
    surface_id: SurfaceId,
    count: int,
    region: str | None = None,
) -> list[CuratedRecommendation]:
    """Fetch section items for NEW_TAB_EN_US and return as flat list.

    Args:
        sections_backend: Backend to fetch corpus sections
        engagement_backend: Backend for engagement data (Thompson sampling)
        prior_backend: Backend for priors (Thompson sampling)
        surface_id: Surface identifier (should be NEW_TAB_EN_US)
        count: Maximum number of recommendations to return
        region: Optional region for engagement filtering (e.g., 'US', 'CA')

    Returns:
        Ranked list of CuratedRecommendation objects
    """
    # 1. Fetch corpus sections (headlines section discarded; only used in sections feed)
    _, corpus_sections = await get_corpus_sections(
        sections_backend=sections_backend,
        surface_id=surface_id,
        min_feed_rank=0,
        include_subtopics=False,
    )

    # 2. Filter to legacy topics only
    legacy_sections = get_corpus_sections_for_legacy_topic(corpus_sections)

    # 3. Extract recommendations, deduplicate, and set scheduledCorpusItemId
    recommendations = extract_recommendations_from_sections(legacy_sections)

    # 4. Filter reported content
    recommendations = takedown_reported_recommendations(
        recommendations,
        engagement_backend=engagement_backend,
        region=region,
    )

    # 5. Apply Thompson sampling (with rescaler=None)
    ranker = ThompsonSamplingRanker(
        engagement_backend=engagement_backend,
        prior_backend=prior_backend,
    )
    recommendations = ranker.rank_items(recommendations, region=region, rescaler=None)

    # 6. Apply publisher spread
    recommendations = spread_publishers(recommendations, spread_distance=3)

    # 7. Limit to count items
    recommendations = recommendations[:count]

    # 8. Renumber receivedRank sequentially (0, 1, 2, ... count-1)
    renumber_recommendations(recommendations)

    # 9. Log error if no recommendations after filtering
    if not recommendations:
        logger.error(
            f"No recommendations available after filtering for surface_id={surface_id}, region={region}"
        )

    return recommendations
