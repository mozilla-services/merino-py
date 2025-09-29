"""Module for building and ranking curated recommendation sections."""

import logging
from collections import defaultdict
from copy import deepcopy
from typing import DefaultDict

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
    CrawlerExperimentRescaler,
)
from merino.curated_recommendations.prior_backends.protocol import PriorBackend, ExperimentRescaler
from merino.curated_recommendations.protocol import (
    CuratedRecommendationsRequest,
    CuratedRecommendation,
    Section,
    SectionConfiguration,
    ExperimentName,
    ProcessedInterests,
    CrawlExperimentBranchName,
    Layout,
)
from merino.curated_recommendations.rankers import (
    thompson_sampling,
    boost_followed_sections,
    section_thompson_sampling,
    put_top_stories_first,
    greedy_personalized_section_rank,
    takedown_reported_recommendations,
)
from merino.curated_recommendations.utils import is_enrolled_in_experiment

logger = logging.getLogger(__name__)

LAYOUT_CYCLE = [layout_6_tiles, layout_4_large, layout_4_medium]
TOP_STORIES_COUNT = 6
DOUBLE_ROW_TOP_STORIES_COUNT = 9
TOP_STORIES_SECTION_EXTRA_COUNT = 5  # Extra top stories pulled from later sections


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


async def _process_corpus_sections(
    corpus_sections_dict: dict[str, CorpusSection],
    min_feed_rank: int,
    surface_id: SurfaceId,
    scheduled_surface_backend: ScheduledSurfaceProtocol | None = None,
) -> dict[str, Section]:
    """Process corpus sections into Section objects with scheduled corpus item mapping.

    Args:
        corpus_sections_dict: Dict mapping section IDs to CorpusSection objects
        min_feed_rank: Starting rank offset for assigning receivedFeedRank
        scheduled_surface_backend: Backend interface to fetch scheduled corpus items
        surface_id: Surface ID for fetching scheduled corpus items

    Returns:
        A mapping from section IDs to Section objects, each with a unique receivedFeedRank
    """
    sid_map: dict[str, str | None] = {}
    if scheduled_surface_backend is not None:
        legacy_corpus = await scheduled_surface_backend.fetch(surface_id)
        for item in legacy_corpus:
            if item.scheduledCorpusItemId is not None:
                sid_map[item.corpusItemId] = item.scheduledCorpusItemId

    sections: dict[str, Section] = {}
    legacy_sections = get_legacy_topic_ids()

    for section_id, cs in corpus_sections_dict.items():
        rank = len(sections) + min_feed_rank
        sections[section_id] = map_corpus_section_to_section(
            cs, rank, is_legacy_section=section_id in legacy_sections
        )

    for section in sections.values():
        for r in section.recommendations:
            if r.corpusItemId in sid_map:
                r.update_scheduled_corpus_item_id(sid_map[r.corpusItemId])

    return sections


async def get_corpus_sections(
    sections_backend: SectionsProtocol,
    surface_id: SurfaceId,
    min_feed_rank: int,
    crawl_branch: str | None = None,
    include_subtopics: bool = False,
    scheduled_surface_backend: ScheduledSurfaceProtocol | None = None,
) -> dict[str, Section]:
    """Fetch editorially curated sections with optional RSS vs. Zyte experiment filtering.

    Args:
        sections_backend: Backend interface to fetch corpus sections.
        surface_id: Identifier for which surface to fetch sections.
        min_feed_rank: Starting rank offset for assigning receivedFeedRank.
        crawl_branch: The crawl experiment branch name or None.
        include_subtopics: Whether to include subtopic sections.
        scheduled_surface_backend: Backend interface to fetch scheduled corpus items (temporary)

    Returns:
        A mapping from section IDs to Section objects, each with a unique receivedFeedRank.
    """
    # Get raw corpus sections
    raw_corpus_sections = await sections_backend.fetch(surface_id)

    # Apply RSS vs. Zyte experiment filtering
    filtered_corpus_sections = filter_sections_by_crawl_experiment(
        raw_corpus_sections, crawl_branch, include_subtopics
    )

    # Process the sections using the shared logic, passing the dict directly
    return await _process_corpus_sections(
        filtered_corpus_sections,
        min_feed_rank,
        surface_id,
        scheduled_surface_backend,
    )


def exclude_recommendations_from_blocked_sections(
    recommendations: list[CuratedRecommendation],
    requested_sections: list[SectionConfiguration],
) -> list[CuratedRecommendation]:
    """Remove recommendations whose topic matches any blocked section.

    Args:
        recommendations: Original list of recommendations.
        requested_sections: SectionConfiguration objects indicating blocked sections.

    Returns:
        Filtered list of recommendations excluding those in blocked sections.
    """
    blocked_ids = {s.sectionId for s in requested_sections if s.isBlocked}
    return [rec for rec in recommendations if not rec.topic or rec.topic.value not in blocked_ids]


def adjust_ads_in_sections(sections: dict[str, Section]) -> None:
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


def is_contextual_ads_experiment(request: CuratedRecommendationsRequest) -> bool:
    """Return True if the Contextual Ads experiment is enabled."""
    return is_enrolled_in_experiment(
        request, ExperimentName.CONTEXTUAL_AD_EXPERIMENT.value, "treatment"
    )


def is_subtopics_experiment(request: CuratedRecommendationsRequest) -> bool:
    """Return True if subtopics should be included based on experiments.

    Include subtopics if:
    - ML sections experiment is enabled (treatment branch), OR
    - Crawl experiment is in the TREATMENT_CRAWL_PLUS_SUBTOPICS branch
    """
    ml_sections_enabled = is_enrolled_in_experiment(
        request, ExperimentName.ML_SECTIONS_EXPERIMENT.value, "treatment"
    )

    # Get the crawl experiment branch to check if it includes subtopics
    crawl_branch = get_crawl_experiment_branch(request)

    # Include subtopics if ml_sections is enabled OR if in crawl-plus-subtopics branch
    return (
        ml_sections_enabled
        or crawl_branch == CrawlExperimentBranchName.TREATMENT_CRAWL_PLUS_SUBTOPICS.value
    )


def get_crawl_experiment_branch(request: CuratedRecommendationsRequest) -> str | None:
    """Return the branch name for the RSS vs. Zyte experiment, or None if not enrolled.

    Branches:
    - control: Non-crawl legacy topics only
    - treatment-crawl: Crawl legacy topics only
    - treatment-crawl-plus-subtopics: Crawl legacy topics + non-crawl subtopics

    Handles both the regular experiment name and the optin- prefixed version for forced enrollment.
    """
    experiment_name = ExperimentName.RSS_VS_ZYTE_EXPERIMENT.value
    # Check for both the experiment name and the optin- prefixed version (forced enrollment)
    if (
        request.experimentName == experiment_name
        or request.experimentName == f"optin-{experiment_name}"
    ):
        return request.experimentBranch
    return None


def is_crawl_experiment_treatment(request: CuratedRecommendationsRequest) -> bool:
    """Return True if the user is in any treatment branch of the RSS vs. Zyte experiment."""
    branch = get_crawl_experiment_branch(request)
    return branch in [
        CrawlExperimentBranchName.TREATMENT_CRAWL.value,
        CrawlExperimentBranchName.TREATMENT_CRAWL_PLUS_SUBTOPICS.value,
    ]


def get_ranking_rescaler_for_branch(
    request: CuratedRecommendationsRequest,
) -> ExperimentRescaler | None:
    """Get the correct interactions and prior rescaler for the current experiment"""
    if is_crawl_experiment_treatment(request):
        return (
            CrawlerExperimentRescaler()
        )  # note is_subtopics_experiment may also be true in this case
    if is_subtopics_experiment(request):
        return SubsectionsExperimentRescaler()
    return None


def update_received_feed_rank(sections: dict[str, Section]):
    """Set receivedFeedRank such that it is incrementing from 0 to len(sections)"""
    for idx, sid in enumerate(sorted(sections, key=lambda k: sections[k].receivedFeedRank)):
        sections[sid].receivedFeedRank = idx


def get_legacy_topic_ids() -> set[str]:
    """Get the set of legacy topic IDs."""
    return {topic.value for topic in Topic}


def get_corpus_sections_for_legacy_topic(
    corpus_sections: dict[str, Section],
) -> dict[str, Section]:
    """Return corpus sections only those matching legacy topics."""
    legacy_topics = get_legacy_topic_ids()

    return {sid: section for sid, section in corpus_sections.items() if sid in legacy_topics}


def is_crawl_section_id(section_id: str) -> bool:
    """Check if a section ID represents a crawl section.

    Args:
        section_id: The section external ID to check

    Returns:
        True if the section ID ends with '_crawl', False otherwise
    """
    return section_id.endswith("_crawl")


def filter_sections_by_crawl_experiment(
    corpus_sections: list[CorpusSection],
    crawl_branch: str | None,
    include_subtopics: bool = False,
) -> dict[str, CorpusSection]:
    """Filter sections based on RSS vs. Zyte experiment branch.

    Args:
        corpus_sections: List of CorpusSection objects
        crawl_branch: The experiment branch name or None
        include_subtopics: Whether to include subtopic sections

    Returns:
        Filtered sections with _crawl suffix removed from keys for crawl sections
    """
    legacy_topics = get_legacy_topic_ids()
    result = {}

    for section in corpus_sections:
        section_id = section.externalId
        is_crawl_section = is_crawl_section_id(section_id)
        base_id = section_id.replace("_crawl", "") if is_crawl_section else section_id
        is_legacy = base_id in legacy_topics

        # Determine if we should include this section based on the branch
        if crawl_branch in [
            CrawlExperimentBranchName.TREATMENT_CRAWL.value,
            CrawlExperimentBranchName.TREATMENT_CRAWL_PLUS_SUBTOPICS.value,
        ]:
            # Treatment branches: use _crawl for legacy, regular for subtopics
            if is_legacy and is_crawl_section:
                result[base_id] = section
            elif (
                not is_legacy
                and not is_crawl_section
                and crawl_branch == CrawlExperimentBranchName.TREATMENT_CRAWL_PLUS_SUBTOPICS.value
            ):
                # Include non-crawl subtopics only in crawl-plus-subtopics branch
                result[base_id] = section
        else:
            # Control branch or no experiment: use non-_crawl sections
            if not is_crawl_section:
                # Include based on whether subtopics are enabled
                if is_legacy or include_subtopics:
                    result[base_id] = section

    return result


def remove_top_story_recs(
    recommendations: list[CuratedRecommendation], top_stories_rec_ids
) -> list[CuratedRecommendation]:
    """Remove recommendations that were included in the top stories section."""
    return [rec for rec in recommendations if rec.corpusItemId not in top_stories_rec_ids]


def cycle_layouts_for_ranked_sections(sections: dict[str, Section], layout_cycle: list[Layout]):
    """Cycle through layouts & assign final layouts to all ranked sections except 'top_stories_section'"""
    # Exclude top_stories_section from layout cycling
    ranked_sections = [
        section for sid, section in sections.items() if sid != "top_stories_section"
    ]
    for idx, section in enumerate(ranked_sections):
        section.layout = deepcopy(layout_cycle[idx % len(layout_cycle)])


def rank_sections(
    sections: dict[str, Section],
    section_configurations: list[SectionConfiguration] | None,
    engagement_backend: EngagementBackend,
    personal_interests: ProcessedInterests | None,
    experiment_rescaler: ExperimentRescaler | None,
) -> dict[str, Section]:
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


def get_top_story_list(
    items: list[CuratedRecommendation],
    top_count: int,
    extra_count: int = 0,
    extra_source_depth: int = 10,
):
    """Build a top story list of top_count items from a full list. Adds some extra items from further down
    in the list of recs with some care to not use the same topic more than once.

    Args:
     items: Ordered list of stories
     top_count: Number of most popular top stories to extract from the top of the list
     extra_count: Number of extra stories to extract from further down
     extra_source_depth: How deep to search after top stories when finding extras

    Returns: A list of top stories
    """
    max_per_topic = 1

    top_stories = items[:top_count]
    topic_counts: DefaultDict[Topic | None, int] = defaultdict(int)
    extra_items: list[CuratedRecommendation] = []
    for rec in items[
        top_count + extra_source_depth :
    ]:  # Skip some of the top items which we can leave in sections
        if len(extra_items) >= extra_count:
            break
        if topic_counts[rec.topic] < max_per_topic:
            topic_counts[rec.topic] += 1
            extra_items.append(rec)
    top_stories.extend(extra_items)
    for idx, rec in enumerate(top_stories):
        rec.receivedRank = idx
    return top_stories


async def get_sections(
    request: CuratedRecommendationsRequest,
    surface_id: SurfaceId,
    sections_backend: SectionsProtocol,
    scheduled_surface_backend: ScheduledSurfaceProtocol,
    engagement_backend: EngagementBackend,
    prior_backend: PriorBackend,
    personal_interests: ProcessedInterests | None = None,
    region: str | None = None,
) -> dict[str, Section]:
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
    # 1. Get corpus sections with RSS vs. Zyte experiment filtering
    crawl_branch = get_crawl_experiment_branch(request)

    # Determine if we should include subtopics based on experiments
    include_subtopics = is_subtopics_experiment(request)

    rescaler = get_ranking_rescaler_for_branch(request)

    corpus_sections_all = await get_corpus_sections(
        sections_backend=sections_backend,
        surface_id=surface_id,
        min_feed_rank=1,
        crawl_branch=crawl_branch,
        include_subtopics=include_subtopics,
        scheduled_surface_backend=scheduled_surface_backend,
    )

    # 2. Sections are already properly filtered by get_corpus_sections
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

    # 5. Remove reported recommendations
    all_remaining_corpus_recommendations = takedown_reported_recommendations(
        all_corpus_recommendations,
        engagement_backend=engagement_backend,
        region=region,
    )

    # 6. Update corpus_sections to make sure reported takedown recs are not present
    remaining_ids = {rec.corpusItemId for rec in all_remaining_corpus_recommendations}
    for cs in corpus_sections.values():
        cs.recommendations = [
            rec for rec in cs.recommendations if rec.corpusItemId in remaining_ids
        ]

    # 7. Rank all corpus recommendations globally by engagement to build top_stories_section
    all_ranked_corpus_recommendations = thompson_sampling(
        all_remaining_corpus_recommendations,
        engagement_backend=engagement_backend,
        prior_backend=prior_backend,
        region=region,
        rescaler=rescaler,
    )

    # 8. Split top stories
    # Use 2-row layout as default for Popular Today
    top_stories_count = DOUBLE_ROW_TOP_STORIES_COUNT
    popular_today_layout = layout_7_tiles_2_ads
    if is_contextual_ads_experiment(request):
        popular_today_layout = layout_4_large

    top_stories = get_top_story_list(
        all_ranked_corpus_recommendations, top_stories_count, TOP_STORIES_SECTION_EXTRA_COUNT
    )

    top_stories_rec_ids = {rec.corpusItemId for rec in top_stories}

    # 9. Remove top story recs from original corpus sections
    for cs in corpus_sections.values():
        cs.recommendations = remove_top_story_recs(cs.recommendations, top_stories_rec_ids)

    # 10. Rank remaining recs in sections by engagement
    for cs in corpus_sections.values():
        cs.recommendations = thompson_sampling(
            cs.recommendations,
            engagement_backend=engagement_backend,
            prior_backend=prior_backend,
            region=region,
            rescaler=rescaler,
        )

    # 11. Initialize sections with top stories
    sections: dict[str, Section] = {
        "top_stories_section": Section(
            receivedFeedRank=0,
            recommendations=top_stories,
            title=get_translation(surface_id, "top-stories", "Popular Today"),
            layout=deepcopy(popular_today_layout),
        )
    }

    # 12. Add remaining corpus sections
    sections.update(corpus_sections)

    # 13. Prune undersized sections
    sections = get_sections_with_enough_items(sections)

    # 14. Rank the sections according to follows and engagement. 'Top Stories' goes at the top.
    sections = rank_sections(
        sections,
        request.sections,
        engagement_backend,
        personal_interests,
        experiment_rescaler=rescaler,
    )

    # 15. Apply final layout cycling to ranked sections except top_stories
    cycle_layouts_for_ranked_sections(sections, LAYOUT_CYCLE)

    # 16. Apply ad adjustments
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
