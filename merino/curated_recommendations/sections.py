"""Module for building and ranking curated recommendation sections."""

import logging
from copy import deepcopy
from typing import Dict, List, Optional

from merino.curated_recommendations import EngagementBackend
from merino.curated_recommendations.corpus_backends.protocol import (
    SectionsProtocol,
    SurfaceId,
    CorpusSection,
    CorpusItem,
    Topic,
)
from merino.curated_recommendations.layouts import (
    layout_4_medium,
    layout_4_large,
    layout_6_tiles,
    layout_3_ads,
)
from merino.curated_recommendations.localization import get_translation
from merino.curated_recommendations.prior_backends.protocol import PriorBackend
from merino.curated_recommendations.protocol import (
    CuratedRecommendationsRequest,
    CuratedRecommendation,
    Section,
    SectionConfiguration,
    ExperimentName,
    InferredInterests,
    Layout,
)
from merino.curated_recommendations.rankers import (
    thompson_sampling,
    boost_followed_sections,
    section_thompson_sampling,
    put_top_stories_first,
    greedy_personalized_section_rank,
)
from merino.curated_recommendations.utils import is_enrolled_in_experiment

logger = logging.getLogger(__name__)

LAYOUT_CYCLE = [layout_6_tiles, layout_4_large, layout_4_medium]
TOP_STORIES_COUNT = 6


def map_topic_to_iab_categories(topic: Topic) -> list[str]:
    """Map a topic to IAB category code(s). Source:
    https://docs.google.com/spreadsheets/d/1R0wzDYgrFkLjo6sxTFvVYThJ4uKz-YVDkYMegbGK9XA/edit?gid=1439764175#gid
    =1439764175

    Args:
        topic: The topic for which to get IAB category code(s).

    Returns:
        Array of IAB codes for given section_topic.
    """
    topic_iab_category_mapping = {
        Topic.BUSINESS: ["52"],  # IAB -  Business and Finance
        Topic.CAREER: ["123"],  # IAB -  Careers
        Topic.EDUCATION: ["132"],  # IAB -  Education
        Topic.ARTS: ["JLBCU7"],  # IAB -  Entertainment
        Topic.FOOD: ["210"],  # IAB -  Food & Drink
        Topic.HEALTH_FITNESS: ["223"],  # IAB -  Healthy Living
        Topic.HOME: ["274"],  # IAB -  Home & Garden
        Topic.PERSONAL_FINANCE: ["391"],  # IAB -  Personal Finance
        Topic.POLITICS: ["386"],  # IAB -  Politics
        Topic.SPORTS: ["483"],  # IAB -  Sports
        Topic.TECHNOLOGY: ["596"],  # IAB -  Technology & Computing
        Topic.TRAVEL: ["653"],  # IAB -  Travel
        Topic.GAMING: ["596"],  # IAB -  Technology & Computing
        Topic.PARENTING: ["192"],  # IAB -  Parenting
        Topic.SCIENCE: ["464"],  # IAB -  Science
        Topic.SELF_IMPROVEMENT: ["186"],  # IAB -  Family and Relationships
    }
    return topic_iab_category_mapping.get(topic) or []


def map_section_item_to_recommendation(
    item: CorpusItem,
    rank: int,
    section_id: str,
) -> CuratedRecommendation:
    """Map a CorpusItem to a CuratedRecommendation.

    Args:
        item: The corpus item to map.
        rank: The received rank of the recommendation.
        section_id: The external ID of the section used for the features key.

    Returns:
        A CuratedRecommendation.
    """
    # We use a feature prefix of "t_" for topics and "s_" for sections
    features = {f"s_{section_id}": 1.0}
    if item.topic is not None:
        features[f"t_{item.topic}"] = 1.0

    return CuratedRecommendation(
        **item.model_dump(),
        receivedRank=rank,
        # Treat the section’s externalId as a weight-1.0 feature so the client can aggregate a
        # coarse interest vector. See also https://mozilla-hub.atlassian.net/wiki/x/FoV5Ww
        features=features,
    )


def map_corpus_section_to_section(
    corpus_section: CorpusSection, rank: int, layout: Layout
) -> Section:
    """Map a CorpusSection to a Section with recommendations.

    Args:
        corpus_section: The corpus section to map.
        rank: The receivedFeedRank to assign to this section.
        layout: The layout for the Section.
        which determines how the client orders the sections.

    Returns:
        A Section model containing mapped recommendations and default layout.
    """
    recommendations = [
        map_section_item_to_recommendation(item, rank, corpus_section.externalId)
        for rank, item in enumerate(corpus_section.sectionItems)
    ]
    return Section(
        receivedFeedRank=rank,
        recommendations=recommendations,
        title=corpus_section.title,
        iab=corpus_section.iab,
        layout=deepcopy(layout),
    )


async def get_corpus_sections(
    sections_backend: SectionsProtocol,
    surface_id: SurfaceId,
    min_feed_rank: int,
) -> Dict[str, Section]:
    """Fetch editorially curated sections from the sections backend.

    Args:
        sections_backend: Backend interface to fetch corpus sections.
        surface_id: Identifier for which surface to fetch sections.
        min_feed_rank: Starting rank offset for assigning receivedFeedRank.

    Returns:
        A mapping from section IDs to Section objects, each with a unique receivedFeedRank.
    """
    corpus_sections = await sections_backend.fetch(surface_id)
    sections: Dict[str, Section] = {}

    for cs in corpus_sections:
        rank = len(sections) + min_feed_rank
        sections[cs.externalId] = map_corpus_section_to_section(
            cs, rank, LAYOUT_CYCLE[len(sections) % len(LAYOUT_CYCLE)]
        )
    return sections


def exclude_recommendations_from_blocked_sections(
    recommendations: List[CuratedRecommendation],
    requested_sections: List[SectionConfiguration],
) -> List[CuratedRecommendation]:
    """Remove recommendations whose topic matches any blocked section.

    Args:
        recommendations: Original list of recommendations.
        requested_sections: SectionConfiguration objects indicating blocked sections.

    Returns:
        Filtered list of recommendations excluding those in blocked sections.
    """
    blocked_ids = {s.sectionId for s in requested_sections if s.isBlocked}
    return [rec for rec in recommendations if not rec.topic or rec.topic.value not in blocked_ids]


def set_double_row_layout(sections: Dict[str, Section]) -> None:
    """Apply a 3-ad, double-row layout to the second section if it exists and has enough items.

    Args:
        sections: Mapping of section IDs to Section objects (with current ReceivedFeedRank).

    Returns:
        None. Mutates the Section.layout in-place.
    """
    second = next(
        (s for s in sections.values() if s.receivedFeedRank == 1),
        None,
    )
    if second and len(second.recommendations) >= layout_3_ads.max_tile_count:
        second.layout = layout_3_ads


def adjust_ads_in_sections(sections: Dict[str, Section]) -> None:
    """Disable ads in all sections except the first, second, third, fifth, seventh, and ninth.

    Args:
        sections: Mapping of section IDs to Section objects.

    Returns:
        None. Mutates tile.hasAd flags in-place.
    """
    allowed = {0, 1, 2, 4, 6, 8}
    for sec in sections.values():
        if sec.receivedFeedRank in allowed:
            continue
        for rl in sec.layout.responsiveLayouts:
            for tile in rl.tiles:
                tile.hasAd = False


def is_ml_sections_experiment(request: CuratedRecommendationsRequest) -> bool:
    """Return True if the sections backend experiment is enabled."""
    return is_enrolled_in_experiment(
        request, ExperimentName.ML_SECTIONS_EXPERIMENT.value, "treatment"
    )


def update_received_feed_rank(sections: Dict[str, Section]):
    """Set receivedFeedRank such that it is incrementing from 0 to len(sections)"""
    for idx, sid in enumerate(sorted(sections, key=lambda k: sections[k].receivedFeedRank)):
        sections[sid].receivedFeedRank = idx


def get_corpus_sections_for_legacy_topic(
    corpus_sections: dict[str, Section],
) -> dict[str, Section]:
    """Return corpus sections only those matching legacy topics."""
    legacy_topics = {topic.value for topic in Topic}

    return {sid: section for sid, section in corpus_sections.items() if sid in legacy_topics}


def remove_top_story_recs(
    recommendations: list[CuratedRecommendation], top_stories_rec_ids
) -> (list)[CuratedRecommendation]:
    """Remove recommendations that were included in the top stories section."""
    return [rec for rec in recommendations if rec.corpusItemId not in top_stories_rec_ids]


def rank_sections(
    sections: Dict[str, Section],
    section_configurations: list[SectionConfiguration] | None,
    engagement_backend: EngagementBackend,
    personal_interests: InferredInterests | None,
) -> Dict[str, Section]:
    """Apply a series of stable ranking passes to the sections feed, in order of priority.

    1. Pin the `top_stories_section` to receivedFeedRank 0 so it's always at the top.
    2. Promote any user-followed sections from `section_configurations` to appear immediately
       after Top Stories, ordered by recency (followedAt) and preserving their relative order.
    3. Apply Thompson sampling on engagement data (via `engagement_backend`) to the remaining
       sections for exploration/exploitation balance.

    Args:
        sections: a dict mapping section IDs to Section objects (with `receivedFeedRank` set).
        section_configurations: optional list of SectionConfiguration objects indicating which
            sections are followed/blocked and when they were followed.
        engagement_backend: provides engagement signals for Thompson sampling.

    Returns:
        The same `sections` dict, with each Section’s `receivedFeedRank` updated to the new order.
    """
    # 4th priority: reorder for exploration via Thompson sampling on engagement
    sections = section_thompson_sampling(sections, engagement_backend=engagement_backend)

    # 3rd priority: reorder based on inferred interest vector
    if personal_interests is not None:
        sections = greedy_personalized_section_rank(sections, personal_interests)

    # 2nd priority: boost followed sections, if any
    if section_configurations:
        sections = boost_followed_sections(section_configurations, sections)

    # 1st priority: always keep top stories at the very top
    sections = put_top_stories_first(sections)

    return sections


async def get_sections(
    request: CuratedRecommendationsRequest,
    surface_id: SurfaceId,
    sections_backend: SectionsProtocol,
    engagement_backend: EngagementBackend,
    prior_backend: PriorBackend,
    personal_interests: Optional[InferredInterests] = None,
    region: Optional[str] = None,
) -> Dict[str, Section]:
    """Build, rank, and layout recommendation sections for a "sections" experiment.

    Args:
        request: The full API request containing feeds and section configs.
        surface_id: SurfaceId determining locale-specific titles.
        sections_backend: Backend to fetch editorial ML-generated sections.
        engagement_backend: Backend to fetch click/impression data.
        prior_backend: Backend providing priors for Thompson sampling.
        region: Two-letter region code, or None.

    Returns:
        A dict mapping section IDs to fully-configured Section models.
    """
    # 1. Get ALL corpus sections
    corpus_sections = await get_corpus_sections(sections_backend, surface_id, 1)

    # 2. If ML sections are NOT requested, filter to legacy sections
    if not is_ml_sections_experiment(request):
        corpus_sections = get_corpus_sections_for_legacy_topic(corpus_sections)

    # 3. Filter out blocked topics
    if request.sections:
        for cs in corpus_sections.values():
            cs.recommendations = exclude_recommendations_from_blocked_sections(
                cs.recommendations, request.sections
            )

    # 4. Collect all recommendations across all sections
    all_corpus_recommendations = [
        rec for section in corpus_sections.values() for rec in section.recommendations
    ]

    # 5. Rank all corpus recommendations globally by engagement to build top_stories_section
    all_ranked_corpus_recommendations = thompson_sampling(
        all_corpus_recommendations,
        engagement_backend=engagement_backend,
        prior_backend=prior_backend,
        region=region,
    )

    # 6. Split top stories
    top_stories = all_ranked_corpus_recommendations[:TOP_STORIES_COUNT]
    top_stories_rec_ids = {rec.corpusItemId for rec in top_stories}

    # 7. Remove top story recs from original corpus sections
    for cs in corpus_sections.values():
        cs.recommendations = remove_top_story_recs(cs.recommendations, top_stories_rec_ids)

    # 8. Rank remaining recs in sections by engagement
    for cs in corpus_sections.values():
        cs.recommendations = thompson_sampling(
            cs.recommendations,
            engagement_backend=engagement_backend,
            prior_backend=prior_backend,
            region=region,
        )

    # 9. Initialize sections with top stories
    sections: Dict[str, Section] = {
        "top_stories_section": Section(
            receivedFeedRank=0,
            recommendations=top_stories,
            title=get_translation(surface_id, "top-stories", "Popular Today"),
            layout=deepcopy(layout_4_large),
        )
    }

    # 10. Add remaining corpus sections
    sections.update(corpus_sections)

    # 11. Prune undersized sections
    sections = get_sections_with_enough_items(sections)

    # 12. Rank the sections according to follows and engagement. 'Top Stories' goes at the top.
    sections = rank_sections(sections, request.sections, engagement_backend, personal_interests)

    # 13. Apply ad/layout tweaks
    set_double_row_layout(sections)
    adjust_ads_in_sections(sections)

    return sections


def get_sections_with_enough_items(sections: dict[str, Section]) -> dict[str, Section]:
    """Remove any Section that doesn’t have enough recommendations to fill its layout plus a fallback.

    Args:
        sections: Mapping of section IDs to Section objects.

    Returns:
        A dict containing only those sections where
        len(section.recommendations) >= section.layout.max_tile_count + 1.
    """
    return {
        sid: sec
        for sid, sec in sections.items()
        if len(sec.recommendations) >= sec.layout.max_tile_count + 1
    }
