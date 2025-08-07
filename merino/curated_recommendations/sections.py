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
    ScheduledSurfaceProtocol,
)
from merino.curated_recommendations.layouts import (
    layout_4_medium,
    layout_4_large,
    layout_6_tiles,
    layout_7_tiles_2_ads,
)
from merino.curated_recommendations.localization import get_translation
from merino.curated_recommendations.prior_backends.experiment_rescaler import (
    SubsectionsExperimentRescaler,
    SUBTOPIC_EXPERIMENT_CURATED_ITEM_FLAG,
)
from merino.curated_recommendations.prior_backends.protocol import PriorBackend, ExperimentRescaler
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

LAYOUT_CYCLE = [layout_4_medium, layout_6_tiles, layout_4_large]
TOP_STORIES_COUNT = 6


def map_section_item_to_recommendation(
    item: CorpusItem, rank: int, section_id: str, experiment_flags: set[str] | None = None
) -> CuratedRecommendation:
    """Map a CorpusItem to a CuratedRecommendation.

    Args:
        item: The corpus item to map.
        rank: The received rank of the recommendation.
        section_id: The external ID of the section used for the features key.
        experiment_flags: A set indicating special memberships of the content item
    Returns:
        A CuratedRecommendation.
    """
    # We use a feature prefix of "t_" for topics and "s_" for sections
    features = {f"s_{section_id}": 1.0}
    if item.topic is not None:
        features[f"t_{item.topic.value}"] = 1.0

    return CuratedRecommendation(
        **item.model_dump(),
        receivedRank=rank,
        # Treat the section’s externalId as a weight-1.0 feature so the client can aggregate a
        # coarse interest vector. See also https://mozilla-hub.atlassian.net/wiki/x/FoV5Ww
        features=features,
        experiment_flags=experiment_flags,
    )


def map_corpus_section_to_section(
    corpus_section: CorpusSection,
    rank: int,
    layout: Layout = layout_6_tiles,
    is_legacy_section: bool = False,
) -> Section:
    """Map a CorpusSection to a Section with recommendations.

    Args:
        corpus_section: The corpus section to map.
        rank: The receivedFeedRank to assign to this section.
        which determines how the client orders the sections.
        layout: The layout for the Section. Defaults to layout_6_tiles to ensure
        Sections have enough recs for the biggest layout.
        is_legacy_section: If section is one of the standard historical sections

    Returns:
        A Section model containing mapped recommendations and default layout.
    """
    item_flags = set() if is_legacy_section else {SUBTOPIC_EXPERIMENT_CURATED_ITEM_FLAG}
    recommendations = [
        map_section_item_to_recommendation(
            item, rank, corpus_section.externalId, experiment_flags=item_flags
        )
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
    scheduled_surface_backend: ScheduledSurfaceProtocol | None = None,
) -> Dict[str, Section]:
    """Fetch editorially curated sections from the sections backend.

    Args:
        sections_backend: Backend interface to fetch corpus sections.
        surface_id: Identifier for which surface to fetch sections.
        min_feed_rank: Starting rank offset for assigning receivedFeedRank.
        scheduled_surface_backend: Backend interface to fetch scheduled corpus items (temporary)

    Returns:
        A mapping from section IDs to Section objects, each with a unique receivedFeedRank.
    """
    corpus_sections = await sections_backend.fetch(surface_id)
    sid_map: Dict[str, str | None] = {}
    if scheduled_surface_backend is not None:
        legacy_corpus = await scheduled_surface_backend.fetch(surface_id)
        for item in legacy_corpus:
            if item.scheduledCorpusItemId is not None:
                sid_map[item.corpusItemId] = item.scheduledCorpusItemId

    sections: Dict[str, Section] = {}

    legacy_sections = {topic.value for topic in Topic}
    for cs in corpus_sections:
        rank = len(sections) + min_feed_rank
        sections[cs.externalId] = map_corpus_section_to_section(
            cs, rank, is_legacy_section=cs.externalId in legacy_sections
        )
    for sname, section in sections.items():
        for r in section.recommendations:
            if r.corpusItemId in sid_map:
                r.update_scheduled_corpus_item_id(sid_map[r.corpusItemId])
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


def is_popular_today_double_row_layout(request: CuratedRecommendationsRequest) -> bool:
    """Return True for the treatment branch of the ML sub-topics experiment, otherwise False."""
    return is_ml_sections_experiment(request)


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
) -> list[CuratedRecommendation]:
    """Remove recommendations that were included in the top stories section."""
    return [rec for rec in recommendations if rec.corpusItemId not in top_stories_rec_ids]


def cycle_layouts_for_ranked_sections(
    sections: dict[str, Section], layout_cycle: list[Layout] | None = None
):
    """Cycle through layouts & assign final layouts to all ranked sections except 'top_stories_section'"""
    if not layout_cycle:
        layout_cycle = LAYOUT_CYCLE
    # Exclude top_stories_section from layout cycling
    ranked_sections = [
        section for sid, section in sections.items() if sid != "top_stories_section"
    ]
    for idx, section in enumerate(ranked_sections):
        section.layout = deepcopy(layout_cycle[idx % len(layout_cycle)])


def rank_sections(
    sections: Dict[str, Section],
    section_configurations: list[SectionConfiguration] | None,
    engagement_backend: EngagementBackend,
    personal_interests: InferredInterests | None,
    experiment_rescaler: ExperimentRescaler | None,
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
        personal_interests: provides personal interests.
        experiment_rescaler: Rescaler that can rescale based on experiment size

    Returns:
        The same `sections` dict, with each Section’s `receivedFeedRank` updated to the new order.
    """
    # 4th priority: reorder for exploration via Thompson sampling on engagement
    sections = section_thompson_sampling(
        sections, engagement_backend=engagement_backend, rescaler=experiment_rescaler
    )

    # 3rd priority: reorder based on inferred interest vector
    if personal_interests is not None:
        sections = greedy_personalized_section_rank(sections, personal_interests)

    # 2nd priority: boost followed sections, if any
    if section_configurations:
        sections = boost_followed_sections(section_configurations, sections)

    # 1st priority: always keep top stories at the very top
    sections = put_top_stories_first(sections)

    # Sort sections by receivedFeedRank
    sections = {
        sid: section
        for sid, section in sorted(sections.items(), key=lambda kv: kv[1].receivedFeedRank)
    }

    return sections


async def get_sections(
    request: CuratedRecommendationsRequest,
    surface_id: SurfaceId,
    sections_backend: SectionsProtocol,
    scheduled_surface_backend: ScheduledSurfaceProtocol,
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
    corpus_sections_all = await get_corpus_sections(
        sections_backend=sections_backend,
        surface_id=surface_id,
        min_feed_rank=1,
        scheduled_surface_backend=scheduled_surface_backend,
    )

    # 2. If ML sections are NOT requested, filter to legacy sections
    subtopic_experiment_enabled = is_ml_sections_experiment(request)
    if not subtopic_experiment_enabled:
        corpus_sections = get_corpus_sections_for_legacy_topic(corpus_sections_all)
    else:
        corpus_sections = corpus_sections_all
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

    rescaler = SubsectionsExperimentRescaler() if subtopic_experiment_enabled else None

    # 5. Rank all corpus recommendations globally by engagement to build top_stories_section
    all_ranked_corpus_recommendations = thompson_sampling(
        all_corpus_recommendations,
        engagement_backend=engagement_backend,
        prior_backend=prior_backend,
        region=region,
        rescaler=rescaler,
    )

    # 6. Split top stories
    top_stories_count = TOP_STORIES_COUNT
    layout_cycle = LAYOUT_CYCLE
    popular_today_layout = layout_4_large

    # check if popular today double row experiment is enabled
    # update top story count & layout cycle
    if is_popular_today_double_row_layout(request):
        top_stories_count = 9
        layout_cycle = [layout_6_tiles, layout_4_large, layout_4_medium]
        popular_today_layout = layout_7_tiles_2_ads

    top_stories = all_ranked_corpus_recommendations[:top_stories_count]

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
            rescaler=rescaler,
        )

    # 9. Initialize sections with top stories
    sections: Dict[str, Section] = {
        "top_stories_section": Section(
            receivedFeedRank=0,
            recommendations=top_stories,
            title=get_translation(surface_id, "top-stories", "Popular Today"),
            layout=deepcopy(popular_today_layout),
        )
    }

    # 10. Add remaining corpus sections
    sections.update(corpus_sections)

    # 11. Prune undersized sections
    sections = get_sections_with_enough_items(sections)

    # 12. Rank the sections according to follows and engagement. 'Top Stories' goes at the top.
    sections = rank_sections(
        sections,
        request.sections,
        engagement_backend,
        personal_interests,
        experiment_rescaler=rescaler,
    )

    # 13. Apply final layout cycling to ranked sections except top_stories
    cycle_layouts_for_ranked_sections(sections, layout_cycle)

    # 14. Apply ad adjustments
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
