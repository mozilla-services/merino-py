"""Module for building and ranking curated recommendation sections."""

import logging
from copy import deepcopy

from merino.curated_recommendations import EngagementBackend
from merino.curated_recommendations.corpus_backends.protocol import (
    SectionsProtocol,
    SurfaceId,
    CorpusSection,
    CorpusItem,
    Topic,
    CreateSource,
)
from merino.curated_recommendations.layouts import (
    layout_4_medium,
    layout_4_large,
    layout_6_tiles,
    layout_7_tiles_2_ads,
)
from merino.curated_recommendations.localization import get_translation
from merino.curated_recommendations.ml_backends.protocol import MLRecsBackend
from merino.curated_recommendations.ml_backends.static_local_model import (
    CONTEXTUAL_RANKING_TREATMENT_COUNTRY,
    CONTEXTUAL_RANKING_TREATMENT_TZ,
)
from merino.curated_recommendations.prior_backends.engagment_rescaler import (
    CrawledContentRescaler,
    SchedulerHoldbackRescaler,
    UKCrawledContentRescaler,
)
from merino.curated_recommendations.prior_backends.protocol import PriorBackend, EngagementRescaler
from merino.curated_recommendations.protocol import (
    ITEM_SUBTOPIC_FLAG,
    CuratedRecommendationsRequest,
    CuratedRecommendation,
    Section,
    SectionConfiguration,
    ExperimentName,
    DailyBriefingBranch,
    ProcessedInterests,
    Layout,
)
from merino.curated_recommendations.article_balancer import TopStoriesArticleBalancer
from merino.curated_recommendations.rankers import (
    ContextualRanker,
    Ranker,
    ThompsonSamplingRanker,
    filter_fresh_items_with_probability,
    boost_followed_sections,
    put_top_stories_first,
    greedy_personalized_section_rank,
    TOP_STORIES_SECTION_KEY,
    takedown_reported_recommendations,
)
from merino.curated_recommendations.utils import is_enrolled_in_experiment

logger = logging.getLogger(__name__)

LAYOUT_CYCLE = [layout_6_tiles, layout_4_large, layout_4_medium]
TOP_STORIES_COUNT = 6
DOUBLE_ROW_TOP_STORIES_COUNT = 9
TOP_STORIES_SECTION_EXTRA_COUNT = 5  # Extra top stories pulled from later sections
HEADLINES_SECTION_KEY = "headlines"
# Require enough recommendations to fill the layout plus a single fallback item
SECTION_FALLBACK_BUFFER = 1


def map_section_item_to_recommendation(
    item: CorpusItem,
    rank: int,
    section_id: str,
    experiment_flags: set[str] | None = None,
    is_manual_section: bool = False,
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
    features = {} if is_manual_section else {f"s_{section_id}": 1.0}
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
    item_flags = set()
    is_manual_section = corpus_section.createSource == CreateSource.MANUAL
    if not is_legacy_section and not is_manual_section:
        item_flags.add(ITEM_SUBTOPIC_FLAG)
    seen_ids: set[str] = set()
    section_items: list[CorpusItem] = []
    for item in corpus_section.sectionItems:
        if item.corpusItemId in seen_ids:
            continue
        seen_ids.add(item.corpusItemId)
        section_items.append(item)
    recommendations = [
        map_section_item_to_recommendation(
            item,
            rank,
            corpus_section.externalId,
            experiment_flags=item_flags,
            is_manual_section=is_manual_section,
        )
        for rank, item in enumerate(section_items)
    ]
    return Section(
        receivedFeedRank=rank,
        recommendations=recommendations,
        title=corpus_section.title,
        subtitle=corpus_section.description,
        heroTitle=corpus_section.heroTitle,
        heroSubtitle=corpus_section.heroSubtitle,
        iab=corpus_section.iab,
        layout=deepcopy(layout),
    )


def _process_corpus_sections(
    corpus_sections_dict: dict[str, CorpusSection],
    min_feed_rank: int,
) -> dict[str, Section]:
    """Process corpus sections into Section objects.

    Args:
        corpus_sections_dict: Dict mapping section IDs to CorpusSection objects
        min_feed_rank: Starting rank offset for assigning receivedFeedRank

    Returns:
        A mapping from section IDs to Section objects, each with a unique receivedFeedRank
    """
    sections: dict[str, Section] = {}
    legacy_sections = get_legacy_topic_ids()

    for section_id, cs in corpus_sections_dict.items():
        rank = len(sections) + min_feed_rank
        sections[section_id] = map_corpus_section_to_section(
            cs, rank, is_legacy_section=section_id in legacy_sections
        )

    return sections


async def get_corpus_sections(
    sections_backend: SectionsProtocol,
    surface_id: SurfaceId,
    min_feed_rank: int,
    include_subtopics: bool = False,
) -> tuple[Section | None, dict[str, Section]]:
    """Fetch curated sections.

    Args:
        sections_backend: Backend interface to fetch corpus sections.
        surface_id: Identifier for which surface to fetch sections.
        min_feed_rank: Starting rank offset for assigning receivedFeedRank.
        include_subtopics: Whether to include subtopic sections.

    Returns:
        A tuple of headlines section (if present) & a mapping from section IDs to Section objects, each with a unique receivedFeedRank.
    """
    # Get raw corpus sections
    raw_corpus_sections = await sections_backend.fetch(surface_id)

    # Split headlines_section & remaining sections
    raw_headlines_section, remaining_raw_corpus_sections = split_headlines_section(
        raw_corpus_sections
    )
    headlines_corpus_section: Section | None = None

    # If Headlines section is present, isolate from other sections & map to a corpus section
    if raw_headlines_section:
        headlines_corpus_section = map_corpus_section_to_section(
            corpus_section=raw_headlines_section,
            rank=0,
            layout=deepcopy(layout_4_large),
            is_legacy_section=False,
        )

    # Apply filtering based on subtopics experiment
    filtered_corpus_sections = filter_sections_by_experiment(
        remaining_raw_corpus_sections,
        include_subtopics,
    )

    # Process the sections using the shared logic
    corpus_sections = _process_corpus_sections(
        filtered_corpus_sections,
        min_feed_rank,
    )

    return headlines_corpus_section, corpus_sections


def split_headlines_section(
    corpus_sections: list[CorpusSection],
) -> tuple[CorpusSection | None, list[CorpusSection]]:
    """Return the headlines section separately from everything else."""
    headlines_section: CorpusSection | None = None
    remaining_sections: list[CorpusSection] = []
    for cs in corpus_sections:
        if cs.externalId == HEADLINES_SECTION_KEY:
            headlines_section = cs
        else:
            remaining_sections.append(cs)
    return headlines_section, remaining_sections


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
    """Return True if any of the 6 Contextual Ads experiments are enabled."""
    contextual_ads_experiments = [
        ExperimentName.CONTEXTUAL_AD_NIGHTLY_EXPERIMENT.value,
        ExperimentName.CONTEXTUAL_AD_V2_NIGHTLY_EXPERIMENT.value,
        ExperimentName.CONTEXTUAL_AD_BETA_EXPERIMENT.value,
        ExperimentName.CONTEXTUAL_AD_V2_BETA_EXPERIMENT.value,
        ExperimentName.CONTEXTUAL_AD_RELEASE_EXPERIMENT.value,
        ExperimentName.CONTEXTUAL_AD_V2_RELEASE_EXPERIMENT.value,
    ]
    return any(
        is_enrolled_in_experiment(request, exp_name, "treatment")
        for exp_name in contextual_ads_experiments
    )


def is_inferred_contextual_ranking(
    _request: CuratedRecommendationsRequest, personal_interests: ProcessedInterests | None
) -> bool:
    """Return True if inferred contextual ranking should be applied."""
    INFERRED_ENABLED_MOD_SELECTOR = (
        4  # 25% of inferred users are going to go to the contextual ranking
    )
    return (
        personal_interests is not None
        and personal_interests.cohort is not None
        and personal_interests.numerical_value % INFERRED_ENABLED_MOD_SELECTOR == 0
    )


def is_daily_briefing_experiment(request: CuratedRecommendationsRequest) -> bool:
    """Return True if the Daily Briefing Section experiment is enabled (either branch)."""
    experiment_name = ExperimentName.DAILY_BRIEFING_EXPERIMENT.value
    return is_enrolled_in_experiment(
        request, experiment_name, DailyBriefingBranch.BRIEFING_WITH_POPULAR.value
    ) or is_enrolled_in_experiment(
        request, experiment_name, DailyBriefingBranch.BRIEFING_WITHOUT_POPULAR.value
    )


def should_show_popular_today_with_headlines(request: CuratedRecommendationsRequest) -> bool:
    """Return True if Popular Today should be shown alongside the headlines section.

    Returns True when user is in the 'briefing-with-popular' branch of the Daily Briefing experiment.
    Returns False when user is in the 'briefing-without-popular' branch.
    """
    return is_enrolled_in_experiment(
        request,
        ExperimentName.DAILY_BRIEFING_EXPERIMENT.value,
        DailyBriefingBranch.BRIEFING_WITH_POPULAR.value,
    )


def is_subtopics_experiment(request: CuratedRecommendationsRequest) -> bool:
    """Return True if subtopics should be included based on experiments.

    Include subtopics if:
    - ML sections experiment is enabled (treatment branch), OR
    """
    in_holdback = is_scheduler_holdback_experiment(request)
    return not in_holdback and request.region in ("US", "GB", "IE")


def is_scheduler_holdback_experiment(request: CuratedRecommendationsRequest) -> bool:
    """Return True if in scheduler holdback expereiment."""
    return is_enrolled_in_experiment(
        request, ExperimentName.SCHEDULER_HOLDBACK_EXPERIMENT.value, "control"
    )


def is_custom_sections_experiment(request: CuratedRecommendationsRequest) -> bool:
    """Return True if custom sections should be included based on experiments."""
    return is_enrolled_in_experiment(
        request, ExperimentName.NEW_TAB_CUSTOM_SECTIONS_EXPERIMENT.value, "treatment"
    )


def is_contextual_ranking_experiment(request: CuratedRecommendationsRequest) -> bool:
    """Return True if the contextual ranking experiment is enabled."""
    return is_enrolled_in_experiment(
        request,
        ExperimentName.CONTEXTUAL_RANKING_CONTENT_EXPERIMENT.value,
        CONTEXTUAL_RANKING_TREATMENT_TZ,
    ) or is_enrolled_in_experiment(
        request,
        ExperimentName.CONTEXTUAL_RANKING_CONTENT_EXPERIMENT.value,
        CONTEXTUAL_RANKING_TREATMENT_COUNTRY,
    )


def get_ranking_rescaler_for_branch(
    request: CuratedRecommendationsRequest,
    surface_id: SurfaceId | None = None,
) -> EngagementRescaler | None:
    """Get the correct interactions and prior rescaler for the current experiment"""
    if is_scheduler_holdback_experiment(request):
        return SchedulerHoldbackRescaler()

    if surface_id == SurfaceId.NEW_TAB_EN_GB:
        return UKCrawledContentRescaler()

    # While we preivously returned None for non-US, we know there are some section users
    # who may not be in the US. This rescaler is required for all markets where data is getting
    # added throughout the day.

    return CrawledContentRescaler()


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


def filter_sections_by_experiment(
    corpus_sections: list[CorpusSection],
    include_subtopics: bool = False,
) -> dict[str, CorpusSection]:
    """Filter sections based on createSource and subtopics experiment.

    Sections are included if they meet any of these criteria:
    - Manually created sections (createSource == MANUAL)
    - ML-generated legacy topic sections
    - ML-generated subtopic sections (when subtopics experiment is enabled)

    Args:
        corpus_sections: List of CorpusSection objects
        include_subtopics: Whether to include ML subtopic sections

    Returns:
        Dict mapping section IDs to CorpusSection objects
    """
    legacy_topics = get_legacy_topic_ids()
    result = {}

    for section in corpus_sections:
        section_id = section.externalId
        base_id = section_id
        is_legacy = base_id in legacy_topics
        is_manual_section = section.createSource == CreateSource.MANUAL

        if is_manual_section or is_legacy or include_subtopics:
            result[base_id] = section

    return result


def dedupe_recommendations_across_sections(sections: dict[str, Section]) -> dict[str, Section]:
    """Remove duplicate recommendations across sections keeping those in higher-priority sections."""
    seen_ids: set[str] = set()
    deduped_sections: dict[str, Section] = {}

    for section_id, section in sorted(sections.items(), key=lambda kv: kv[1].receivedFeedRank):
        filtered_recs: list[CuratedRecommendation] = []
        section_seen: set[str] = set()
        for rec in section.recommendations:
            if rec.corpusItemId in seen_ids or rec.corpusItemId in section_seen:
                continue
            section_seen.add(rec.corpusItemId)
            filtered_recs.append(rec)

        if len(filtered_recs) < section.layout.max_tile_count + SECTION_FALLBACK_BUFFER:
            continue

        seen_ids.update(section_seen)

        for idx, rec in enumerate(filtered_recs):
            rec.receivedRank = idx

        section.recommendations = filtered_recs
        deduped_sections[section_id] = section

    update_received_feed_rank(deduped_sections)
    return deduped_sections


def cycle_layouts_for_ranked_sections(sections: dict[str, Section], layout_cycle: list[Layout]):
    """Cycle through layouts & assign final layouts to all ranked sections except 'top_stories_section' & 'headlines'."""
    # Exclude top_stories_section & headlines (if present) from layout cycling
    ranked_sections = [
        section
        for sid, section in sections.items()
        if sid not in (HEADLINES_SECTION_KEY, "top_stories_section")
    ]
    for idx, section in enumerate(ranked_sections):
        section.layout = deepcopy(layout_cycle[idx % len(layout_cycle)])


def put_headlines_first_then_top_stories(sections: dict[str, Section]) -> dict[str, Section]:
    """Ensure headlines section is on top followed by top_stories section, other sections should have rank 2...N & preserve relative order."""
    headlines_key = HEADLINES_SECTION_KEY
    top_stories_key = TOP_STORIES_SECTION_KEY

    headlines_section = sections.get(headlines_key)
    top_stories_section = sections.get(top_stories_key)

    if not headlines_section:
        return sections

    # Save & keep relative order for the other sections based on their current ranks
    remaining_sections = sorted(
        (sec for sid, sec in sections.items() if sid not in (headlines_key, top_stories_key)),
        key=lambda s: s.receivedFeedRank,
    )

    # Assign ranks, start with headlines rank == 0
    headlines_section.receivedFeedRank = 0
    # If top_stories is present, assign rank == 1
    if top_stories_section:
        top_stories_section.receivedFeedRank = 1
        rank = 2
    else:
        rank = 1
    # Assign consecutive ranks for the remaining sections
    for idx, section in enumerate(remaining_sections, start=rank):
        section.receivedFeedRank = idx

    return sections


def rank_sections(
    sections: dict[str, Section],
    section_configurations: list[SectionConfiguration] | None,
    ranker: Ranker,
    personal_interests: ProcessedInterests | None,
    engagement_rescaler: EngagementRescaler | None,
    do_section_personalization_reranking: bool = True,
    include_headlines_section: bool = False,
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
        engagement_rescaler: Rescaler that can rescale ranking data based on experiment size and content distribution
        do_section_personalization_reranking: Whether to implement section based reranking for personalization
        if interest vector is avialable.
        include_headlines_section: If headlines experiment is enabled, don't put top_stories_section on top

    Returns:
        The same `sections` dict, with each Section’s `receivedFeedRank` updated to the new order.
    """
    # 4th priority: reorder for exploration via Thompson sampling on engagement
    sections = ranker.rank_sections(sections, rescaler=engagement_rescaler)

    # 3rd priority: reorder based on inferred interest vector
    if do_section_personalization_reranking and personal_interests is not None:
        sections = greedy_personalized_section_rank(sections, personal_interests)

    # 2nd priority: boost followed sections, if any
    if section_configurations:
        sections = boost_followed_sections(section_configurations, sections)

    # 1st priority: always keep top stories at the very top
    sections = put_top_stories_first(sections)

    # If headlines experiment enabled, put headlines section on top, followed by top_stories
    if include_headlines_section:
        put_headlines_first_then_top_stories(sections)

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
    rescaler: EngagementRescaler | None = None,
    relax_constraints_for_personalization=False,
) -> list[CuratedRecommendation]:
    """Build a top story list of top_count items from a full list. Adds some extra items from further down
    in the list of recs with some care to not use the same topic more than once.

    Depending on the rescaler settings, there may be a target limit percentage of items that
    are 'fresh' (i.e have small number of impressions) to balance the initial list.

    Args:
     items: Ordered list of stories
     top_count: Number of most popular top stories to extract from the top of the list
     extra_count: Number of extra stories to extract from further down
     extra_source_depth: How far down to go when picking the extra stories
     rescaler: Optional rescaler associated with the experiment or surface
    Returns: A list of top stories
    """
    constraint_scale = 2.0 if relax_constraints_for_personalization else 1.0

    fresh_story_prob = rescaler.fresh_items_top_stories_max_percentage if rescaler else 0
    total_story_count = top_count + extra_count

    # "Fresh" items are low-impression/new. We throttle (downsample) them to limit their share.
    items_throttled_fresh, unused_fresh = filter_fresh_items_with_probability(
        items,
        fresh_story_prob=fresh_story_prob,
        max_items=total_story_count + extra_source_depth + 10,
        # Extra 10 items to help meet constraints
    )
    non_throttled = items[len(items_throttled_fresh) + len(unused_fresh) :]

    balancer = TopStoriesArticleBalancer(round(top_count * constraint_scale))
    topic_limited_stories, remaining_stories = balancer.add_stories(
        items_throttled_fresh, top_count
    )
    second_pass_candidates = topic_limited_stories + remaining_stories

    if len(second_pass_candidates) > extra_source_depth * 2:
        second_pass_candidates = second_pass_candidates[extra_source_depth:]

    balancer.set_limits_for_expected_articles(round(total_story_count * constraint_scale))
    topic_limited_stories, remaining_stories = balancer.add_stories(
        second_pass_candidates, total_story_count
    )
    top_stories = balancer.get_stories()
    after_second_pass_candidates = topic_limited_stories + remaining_stories
    # If constraints are constraining too much, drop remainder of stories in
    if len(top_stories) < total_story_count:
        remaining_items = after_second_pass_candidates + non_throttled + unused_fresh
        top_stories = top_stories + remaining_items[: total_story_count - len(top_stories)]
    for idx, rec in enumerate(top_stories):
        rec.receivedRank = idx
    return top_stories


async def get_sections(
    request: CuratedRecommendationsRequest,
    surface_id: SurfaceId,
    sections_backend: SectionsProtocol,
    ml_backend: MLRecsBackend,
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
    # Determine if we should include subtopics based on experiments
    include_subtopics = is_subtopics_experiment(request)

    rescaler = get_ranking_rescaler_for_branch(request, surface_id)

    headlines_corpus_section, corpus_sections_all = await get_corpus_sections(
        sections_backend=sections_backend,
        surface_id=surface_id,
        min_feed_rank=1,
        include_subtopics=include_subtopics,
    )

    # Determine if we should include headlines section based on daily briefing experiment
    include_headlines_section = (
        is_daily_briefing_experiment(request) and headlines_corpus_section is not None
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
    ranker: Ranker

    do_inferred_contextual = is_inferred_contextual_ranking(request, personal_interests)
    if (
        (do_inferred_contextual or is_contextual_ranking_experiment(request))
        and ml_backend is not None
        and ml_backend.is_valid()
    ):
        ranker = ContextualRanker(
            engagement_backend=engagement_backend,
            prior_backend=prior_backend,
            ml_backend=ml_backend,
            disable_time_zone_context=request.experimentBranch
            == CONTEXTUAL_RANKING_TREATMENT_COUNTRY,
        )
    else:
        ranker = ThompsonSamplingRanker(
            engagement_backend=engagement_backend, prior_backend=prior_backend
        )

    # 7. Rank all corpus recommendations globally by engagement
    all_ranked_corpus_recommendations = ranker.rank_items(
        all_remaining_corpus_recommendations,
        region=region,
        rescaler=rescaler,
        personal_interests=personal_interests,
        utcOffset=request.utcOffset,
    )
    # 8. Split top stories from the globally ranked recommendations
    # Use 2-row layout as default for Popular Today
    top_stories_count = DOUBLE_ROW_TOP_STORIES_COUNT
    popular_today_layout = layout_7_tiles_2_ads

    if is_contextual_ads_experiment(request):
        popular_today_layout = layout_4_large

    top_stories = get_top_story_list(
        all_ranked_corpus_recommendations,
        top_stories_count,
        TOP_STORIES_SECTION_EXTRA_COUNT,
        rescaler=rescaler,
        relax_constraints_for_personalization=False,  # In the future we can set to true for non-empty personal_interests
    )

    # 9. Create a global rank lookup from the already-ranked recommendations
    # This preserves the Thompson sampling ranking done at step 7 without expensive re-sampling
    global_rank_map = {
        rec.corpusItemId: rank for rank, rec in enumerate(all_ranked_corpus_recommendations)
    }

    # 10. Sort each section's recommendations by their global rank (preserves Thompson sampling order)
    # This is much faster than re-running Thompson sampling for each section
    for cs in corpus_sections.values():
        cs.recommendations = sorted(
            cs.recommendations, key=lambda rec: global_rank_map.get(rec.corpusItemId, float("inf"))
        )
        # Renumber recommendations within each section
        for idx, rec in enumerate(cs.recommendations):
            rec.receivedRank = idx

    # 11. Initialize sections with top stories
    sections: dict[str, Section] = {
        "top_stories_section": Section(
            receivedFeedRank=0,
            recommendations=top_stories,
            title=get_translation(surface_id, "top-stories", "Popular Today"),
            layout=deepcopy(popular_today_layout),
        )
    }

    # 12. If headlines experiment enabled, insert headlines on top
    if is_daily_briefing_experiment(request) and headlines_corpus_section is not None:
        sections[HEADLINES_SECTION_KEY] = headlines_corpus_section
        if should_show_popular_today_with_headlines(request):
            # briefing-with-popular: show both headlines and top_stories (shrink top_stories)
            sections["top_stories_section"].layout = layout_4_medium
        else:
            # briefing-without-popular: remove top_stories entirely
            del sections["top_stories_section"]

    # 13. Add remaining corpus sections
    sections.update(corpus_sections)

    # 14. Prune undersized sections
    sections = get_sections_with_enough_items(sections)

    # 16. Rank the sections according to follows and engagement. 'Top Stories' goes at the top.
    sections = rank_sections(
        sections,
        request.sections,
        ranker,
        personal_interests,
        engagement_rescaler=rescaler,
        include_headlines_section=include_headlines_section,
    )

    # 16. Apply cross-section deduplication, preserving higher-priority sections
    sections = dedupe_recommendations_across_sections(sections)

    # 17. Apply final layout cycling to ranked sections except top_stories
    cycle_layouts_for_ranked_sections(sections, LAYOUT_CYCLE)

    # 18. Apply ad adjustments
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
        if len(sec.recommendations) >= sec.layout.max_tile_count + SECTION_FALLBACK_BUFFER
    }
