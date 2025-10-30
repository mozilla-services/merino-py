"""Algorithms for ranking curated recommendations."""

from collections import deque
from random import random, sample as random_sample

import sentry_sdk
import logging
import math
from copy import copy
from datetime import datetime, timedelta, timezone

from merino.curated_recommendations import ConstantPrior
from merino.curated_recommendations.corpus_backends.protocol import Topic
from merino.curated_recommendations.engagement_backends.protocol import EngagementBackend
from merino.curated_recommendations.ml_backends.static_local_model import DEFAULT_INTERESTS_KEY
from merino.curated_recommendations.prior_backends.protocol import (
    PriorBackend,
    Prior,
    ExperimentRescaler,
)
from merino.curated_recommendations.protocol import (
    CuratedRecommendation,
    SectionConfiguration,
    Section,
    ProcessedInterests,
    RankingData,
)
from scipy.stats import beta
import numpy as np

logger = logging.getLogger(__name__)


def renumber_recommendations(recommendations: list[CuratedRecommendation]) -> None:
    """Renumber the receivedRank of each recommendation to be sequential.

    Args:
        recommendations (list): A list of recommendation objects.
    """
    for rank, rec in enumerate(recommendations):
        rec.receivedRank = rank


def renumber_sections(ordered_sections: list[tuple[str, Section]]) -> dict[str, Section]:
    """Assign receivedFeedRank to each Section based on the list order, and convert it to a dict.

    :param ordered_sections: A list of name + section tuples in the desired order.
    :return: A dict mapping section names to Section objects with receivedFeedRank set.
    """
    result: dict[str, Section] = {}
    for idx, (section_id, section) in enumerate(ordered_sections):
        section.receivedFeedRank = idx
        result[section_id] = section
    return result


# In a weighted average, how much to weigh the metrics from the requested region. 0.95 was chosen
# somewhat arbitrarily in the new-tab-region-specific-content experiment that only targeted Canada.
# CA has about 9x fewer impressions than the total for NEW_TAB_EN_US. A value close to 1 boosts
# regional engagement enough to let it significantly impact the final ranking, while still giving
# some influence to global engagement. It might work equally well for other regions than Canada.
# We could decide later to derive this value dynamically per region.
REGION_ENGAGEMENT_WEIGHT = 0.95

MAX_TOP_REC_SLOTS = 10
NUM_RECS_PER_TOPIC = 2

TOP_STORIES_SECTION_KEY = "top_stories_section"

INFERRED_SCORE_WEIGHT = 0.001

# For taking down reported content
DEFAULT_REPORT_RECS_RATIO_THRESHOLD = 0.001  # using a low number for now (0.1%)
DEFAULT_SAFEGUARD_CAP_TAKEDOWN_FRACTION = 0.50  # allow at most 50% of recs to be auto-removed
DEFAULT_REPORT_COUNT_THRESHOLD = (
    20  # allow recommendation to be auto-removed if it has at least 20 reports
)


def takedown_reported_recommendations(
    recs: list[CuratedRecommendation],
    engagement_backend: EngagementBackend,
    region: str | None = None,
    report_ratio_threshold: float = DEFAULT_REPORT_RECS_RATIO_THRESHOLD,
    safeguard_cap_takedown_fraction: float = DEFAULT_SAFEGUARD_CAP_TAKEDOWN_FRACTION,
) -> list[CuratedRecommendation]:
    """Takedown highly-reported content & return filtered list of recommendations.

      - Exclude any recommendation which breaches (report_count / impression_count) > threshold.
      - Apply a safety cap: allow a certain fraction (50%) of all available recommendations to be taken down automatically.
      - Log an error for the excluded rec, send the error to Sentry.

    :param recs: All recommendations to filter.
    :param engagement_backend: Provides report_count & impression_count data by corpusItemId.
    :param region: Optionally, the client's region, e.g. 'US'.
    :param report_ratio_threshold: Threshold indicating which recommendation should be excluded.
    :param safeguard_cap_takedown_fraction: Max fraction of recommendations that can be auto-removed.

    :return: Filtered list of recommendations.
    """
    # Save engagement metrics for logging: {corpusItemId: (report_ratio, reports, impressions)}
    rec_eng_metrics: dict[str, tuple[float, int, int]] = {}

    def _should_remove(rec: CuratedRecommendation) -> bool:
        if engagement := engagement_backend.get(rec.corpusItemId, region):
            _impressions = int(engagement.impression_count or 0)
            _reports = int(engagement.report_count or 0)
            if _impressions > 0:
                report_ratio = _reports / _impressions
                rec_eng_metrics[rec.corpusItemId] = (report_ratio, _reports, _impressions)
                return (
                    report_ratio > report_ratio_threshold
                    and _reports >= DEFAULT_REPORT_COUNT_THRESHOLD
                )
        return False

    over = [rec for rec in recs if _should_remove(rec)]
    if not over:
        return recs

    # Compute the safeguard cap, # of recs safe to remove from total list of reported_recs
    # rounded up to avoid 0 removals
    max_recs_to_remove = math.ceil(len(recs) * safeguard_cap_takedown_fraction)

    # Sort only the small over-threshold set by ratio; no tie-breakers.
    over.sort(key=lambda r: rec_eng_metrics[r.corpusItemId][0], reverse=True)

    # Select top N to remove
    recs_to_remove = over[:max_recs_to_remove]
    removed_rec_ids = {r.corpusItemId for r in recs_to_remove}

    for rec in recs_to_remove:
        ratio, reports, impressions = rec_eng_metrics.get(rec.corpusItemId, (-1.0, 0, 0))
        # Log a warning for our backend logs
        logger.warning(
            f"Excluding reported recommendation: '{rec.title}' ({rec.url}) was excluded due to high reports",
            extra={
                "corpus_item_id": rec.corpusItemId,
                "report_ratio": ratio,
                "reports": reports,
                "impressions": impressions,
                "threshold": report_ratio_threshold,
                "region": region,
            },
        )

        # Send a structured event to Sentry as a warning 🟡
        sentry_sdk.capture_message(
            f"Excluding reported recommendation: '{rec.title}' ({rec.url}) excluded due to high reports",
            level="warning",
            scope=lambda scope: scope.set_context(
                "excluding reported recommendation",
                {
                    "corpus_item_id": rec.corpusItemId,
                    "title": rec.title,
                    "url": str(rec.url),
                    "report_ratio": ratio,
                    "reports": reports,
                    "impressions": impressions,
                    "threshold": report_ratio_threshold,
                    "region": region,
                },
            ),
        )

    # Return remaining recs
    remaining_recs = [rec for rec in recs if rec.corpusItemId not in removed_rec_ids]
    return remaining_recs


def filter_fresh_items_with_probability(
    items: list[CuratedRecommendation],
    fresh_story_prob: float,
    max_items: int,
) -> tuple[list[CuratedRecommendation], list[CuratedRecommendation]]:
    """Filter recommendations while probabilistically limiting fresh items.

    The function processes ``items`` in order, maintaining a backlog of deferred entries. Before
    evaluating each new item it repeatedly drains that backlog while random draws are below
    ``fresh_story_prob`` so that previously deferred content gets a chance to surface. Fresh
    recommendations (``ranking_data.is_fresh`` truthy) are only admitted when a random draw falls
    below ``fresh_story_prob``; otherwise they are appended to the backlog.

    Args:
        items: Ordered recommendations to evaluate.
        fresh_story_prob: Probability in ``[0, 1]`` controlling how often fresh items are emitted on
            the first pass. Values ``<= 0`` disable probabilistic filtering.
        max_items: Maximum number of recommendations to return in the filtered list.

    Returns:
        tuple[list[CuratedRecommendation], list[CuratedRecommendation]]: The first element contains
        up to ``max_items`` recommendations selected under the probabilistic policy. The second
        element contains the remaining deferred items (all fresh items that were not surfaced and
        any non-fresh items still queued) in their original encounter order.
    """
    filtered_items: list[CuratedRecommendation] = []
    fresh_backlog: deque = deque()

    if max_items == 0:
        return [], []
    if fresh_story_prob <= 0:
        return items[:max_items], []

    for story in items:
        if len(filtered_items) >= max_items:
            break

        ranking_data = getattr(story, "ranking_data", None)
        is_fresh = bool(getattr(ranking_data, "is_fresh", False))

        if not is_fresh:
            filtered_items.append(story)
        else:
            if random() < fresh_story_prob:
                filtered_items.append(story)
            else:
                fresh_backlog.append(story)

        if len(filtered_items) >= max_items:
            break

        while fresh_backlog and random() < fresh_story_prob:
            filtered_items.append(fresh_backlog.popleft())
            if len(filtered_items) >= max_items:
                break

    if len(filtered_items) < max_items and fresh_backlog:
        items_needed = max_items - len(filtered_items)
        for _ in range(items_needed):
            if not fresh_backlog:
                break
            filtered_items.append(fresh_backlog.popleft())

    return filtered_items, list(fresh_backlog)


def thompson_sampling(
    recs: list[CuratedRecommendation],
    engagement_backend: EngagementBackend,
    prior_backend: PriorBackend,
    region: str | None = None,
    region_weight: float = REGION_ENGAGEMENT_WEIGHT,
    rescaler: ExperimentRescaler | None = None,
    personal_interests: ProcessedInterests | None = None,
) -> list[CuratedRecommendation]:
    """Re-rank items using [Thompson sampling][thompson-sampling], combining exploitation of known item
    CTR with exploration of new items using a prior.

    :param recs: A list of recommendations in the desired order (pre-publisher spread).
    :param engagement_backend: Provides aggregate click and impression engagement by corpusItemId.
    :param prior_backend: Provides prior alpha and beta values for Thompson sampling.
    :param region: Optionally, the client's region, e.g. 'US'.
    :param region_weight: In a weighted average, how much to weigh regional engagement.
    :param rescaler: Class that can up-scale interaction stats for certain items based on experiment size
    :param personal_interests User interests

    :return: A re-ordered version of recs, ranked according to the Thompson sampling score.

    [thompson-sampling]: https://en.wikipedia.org/wiki/Thompson_sampling
    """
    fallback_prior = ConstantPrior().get()
    fresh_items_max: int = rescaler.fresh_items_max if rescaler else 0
    fresh_items_limit_prior_threshold_multiplier: float = (
        rescaler.fresh_items_limit_prior_threshold_multiplier if rescaler else 0
    )

    def get_opens_no_opens(
        rec: CuratedRecommendation, region_query: str | None = None
    ) -> tuple[float, float]:
        """Get opens and no-opens counts for a recommendation, optionally in a region."""
        engagement = engagement_backend.get(rec.corpusItemId, region_query)
        if engagement:
            return engagement.click_count, engagement.impression_count - engagement.click_count
        else:
            return 0, 0

    def boost_interest(rec: CuratedRecommendation) -> float:
        if personal_interests is None or rec.topic is None:
            return 0.0
        if rec.topic.value not in personal_interests.normalized_scores:
            return (
                personal_interests.normalized_scores.get(DEFAULT_INTERESTS_KEY, 0.0)
                * INFERRED_SCORE_WEIGHT
            )
        return personal_interests.normalized_scores[rec.topic.value] * INFERRED_SCORE_WEIGHT

    def compute_ranking_scores(rec: CuratedRecommendation):
        """Sample beta distributed from weighted regional/global engagement for a recommendation."""
        opens, no_opens = get_opens_no_opens(rec)

        prior: Prior = prior_backend.get() or fallback_prior
        a_prior = prior.alpha
        b_prior = prior.beta

        # Use a weighted average of regional and global engagement, if that's enabled and available.
        region_opens, region_no_opens = get_opens_no_opens(rec, region)
        region_prior = prior_backend.get(region)
        if region_no_opens and region_prior:
            opens = (region_weight * region_opens) + ((1 - region_weight) * opens)
            no_opens = (region_weight * region_no_opens) + ((1 - region_weight) * no_opens)
            a_prior = (region_weight * region_prior.alpha) + ((1 - region_weight) * a_prior)
            b_prior = (region_weight * region_prior.beta) + ((1 - region_weight) * b_prior)
        non_rescaled_b_prior = b_prior
        if rescaler is not None:
            # rescale for content associated exclusively with an experiment in a specific region
            opens, no_opens = rescaler.rescale(rec, opens, no_opens)
            a_prior, b_prior = rescaler.rescale_prior(rec, a_prior, b_prior)
        # Add priors and ensure opens and no_opens are > 0, which is required by beta.rvs.
        alpha_val = opens + max(a_prior, 1e-18)
        beta_val = no_opens + max(b_prior, 1e-18)
        rec.ranking_data = RankingData(
            score=float(beta.rvs(alpha_val, beta_val)) + boost_interest(rec),
            alpha=alpha_val,
            beta=beta_val,
        )
        if (
            (fresh_items_limit_prior_threshold_multiplier > 0)
            and not rec.isTimeSensitive
            and (no_opens < non_rescaled_b_prior * fresh_items_limit_prior_threshold_multiplier)
        ):
            rec.ranking_data.is_fresh = True

    def suppress_fresh_items(scored_recs: list[CuratedRecommendation]) -> None:
        if fresh_items_max <= 0:
            return

        fresh_items = [
            rec
            for rec in scored_recs
            if rec.ranking_data is not None and rec.ranking_data.is_fresh
        ]
        num_to_remove = len(fresh_items) - fresh_items_max
        if num_to_remove > 0:
            items_to_suppress = random_sample(fresh_items, k=num_to_remove)
            for item in items_to_suppress:
                if item.ranking_data is not None:
                    item.ranking_data.score *= 0.5

    for rec in recs:
        compute_ranking_scores(rec)
    suppress_fresh_items(recs)
    # Sort the recommendations from best to worst sampled score & renumber
    sorted_recs = sorted(
        recs,
        key=lambda r: r.ranking_data.score if r.ranking_data is not None else float("-inf"),
        reverse=True,
    )
    return sorted_recs


def section_thompson_sampling(
    sections: dict[str, Section],
    engagement_backend: EngagementBackend,
    top_n: int = 6,
    rescaler: ExperimentRescaler | None = None,
) -> dict[str, Section]:
    """Re-rank sections using [Thompson sampling][thompson-sampling], based on the combined engagement of top items.

    :param sections: Mapping of section IDs to Section objects whose recommendations will be scored.
    :param engagement_backend: Provides aggregate click and impression engagement by corpusItemId.
    :param top_n: Number of top items in each section for which to sum engagement in the Thompson sampling score.
    :param rescaler: Class that can up-scale interaction stats for certain items based on experiment size

    :return: Mapping of section IDs to Section objects with updated receivedFeedRank.

    [thompson-sampling]: https://en.wikipedia.org/wiki/Thompson_sampling
    """

    def sample_score(sec: Section) -> float:
        """Sample beta distribution for the combined engagement of the top _n_ items."""
        # sum clicks and impressions over top_n items
        rec_pool = sec.recommendations

        fresh_retain_likelyhood = rescaler.fresh_items_section_ranking_max_percentage if rescaler is not None else 0.
        recs, _removed_recs = filter_fresh_items_with_probability(
            sec.recommendations, fresh_story_prob=fresh_retain_likelyhood, max_items=top_n
        )

        total_clicks = 0
        total_imps = 0
        a_prior_total = 0.0
        b_prior_total = 0.0

        # constant prior α, β
        prior = ConstantPrior().get()
        a_prior_per_item = float(prior.alpha)
        b_prior_per_item = float(prior.beta)
        for rec in recs:
            if engagement := engagement_backend.get(rec.corpusItemId):
                clicks = engagement.click_count
                impressions = engagement.impression_count
                if rescaler is not None:
                    # rescale for content associated exclusively with an experiment in a specific experiment
                    clicks, impressions = rescaler.rescale(rec, clicks, impressions)

                total_clicks += clicks
                total_imps += impressions

                if rescaler is not None:
                    a_prior_mod, b_prior_mod = rescaler.rescale_prior(
                        rec, a_prior_per_item, b_prior_per_item
                    )
                    a_prior_total += a_prior_mod
                    b_prior_total += b_prior_mod
                else:
                    a_prior_total += a_prior_per_item
                    b_prior_total += b_prior_per_item

        # Sum engagement and priors.
        opens = max(total_clicks + a_prior_total, 1.0)
        no_opens = max(total_imps - total_clicks + b_prior_total, 1.0)
        # Sample distribution
        return float(beta.rvs(opens, no_opens))

    # sort sections by sampled score, highest first
    ordered = sorted(sections.items(), key=lambda kv: sample_score(kv[1]), reverse=True)
    return renumber_sections(ordered)


def greedy_personalized_section_rank(
    sections: dict[str, Section],
    personal_interests: ProcessedInterests,
    epsilon: float = 0.0,
) -> dict[str, Section]:
    """Insert the ordered personal interest sections into the top of the section ranking.

    Insertion happens for each section with probability 1-epsilon.
      default is to always do the insertion
    """
    ## order init from other functions
    ordered_sections = sorted(sections, key=lambda x: sections[x].receivedFeedRank)

    ## order of personal preferences
    ### only keeps a value if above first coarse threshold. this
    ### is because there is noise added to every value in client and
    ## we do not want to rank on the noise
    ptopics = [k for k, v in personal_interests.scores.items() if v > 0]
    ordered_preferences = sorted(ptopics, key=lambda x: personal_interests.scores[x], reverse=True)

    # decide once for each pref whether it “wins” (prob. 1-epsilon)
    chosen = [
        sec
        for sec in ordered_preferences
        if sec in ordered_sections and np.random.choice([0, 1], p=[epsilon, 1 - epsilon])
    ]

    # append the rest in original order
    rest = [sec for sec in ordered_sections if sec not in chosen]

    # reorder the sections according to the new ranking
    ordered = [(sec, sections[sec]) for sec in chosen + rest]
    return renumber_sections(ordered)


def spread_publishers(
    recs: list[CuratedRecommendation], spread_distance: int
) -> list[CuratedRecommendation]:
    """Spread a list of CuratedRecommendations by the publisher attribute to avoid encountering the same publisher
    in sequence.

    :param recs: The recommendations to be spread
    :param spread_distance: The distance that recs with the same publisher value should be spread apart. The default
        value of None greedily maximizes the distance, by basing the spread distance on the number of unique values.
    :return: CuratedRecommendations spread by publisher, while otherwise preserving the order.
    """
    attr = "publisher"

    result_recs: list[CuratedRecommendation] = []
    remaining_recs = copy(recs)

    while remaining_recs:
        values_to_avoid = set(getattr(r, attr) for r in result_recs[-spread_distance:])
        # Get the first remaining rec which value should not be avoided, or default to the first remaining rec.
        rec = next(
            (r for r in remaining_recs if getattr(r, attr) not in values_to_avoid),
            remaining_recs[0],
        )
        result_recs.append(rec)
        remaining_recs.remove(rec)

    return result_recs


def put_top_stories_first(sections: dict[str, Section]) -> dict[str, Section]:
    """Rank top_stories_section at the top."""
    key = TOP_STORIES_SECTION_KEY
    top_stories = sections.get(TOP_STORIES_SECTION_KEY)
    # If missing or already first, nothing to do
    if not top_stories or top_stories.receivedFeedRank == 0:
        return sections

    # Move top stories to rank 0 and bump others that were above it.
    original_top_stories_rank = top_stories.receivedFeedRank
    top_stories.receivedFeedRank = 0
    for section_id, section in sections.items():
        if section_id != key and section.receivedFeedRank < original_top_stories_rank:
            section.receivedFeedRank += 1
    return sections


def boost_preferred_topic(
    recs: list[CuratedRecommendation],
    preferred_topics: list[Topic],
) -> list[CuratedRecommendation]:
    """Boost recommendations into top N slots based on preferred topics.
    2 recs per topic (for now).

    :param recs: List of recommendations
    :param preferred_topics: User's preferred topic(s)
    :return: CuratedRecommendations ranked based on a preferred topic(s), while otherwise
    preserving the order.
    """
    boosted_recs: list[CuratedRecommendation] = []
    remaining_recs = []
    # The following dict tracks the number of recommendations per topic to be boosted.
    remaining_num_topic_boosts = {
        preferred_topic: NUM_RECS_PER_TOPIC for preferred_topic in preferred_topics
    }

    for rec in recs:
        topic = rec.topic
        # Check if the recommendation should be boosted
        # Boost if slots (e.g. 10) remain and its topic hasn't been boosted too often (e.g. 2).
        # It relies on get() returning None for missing keys, and None and 0 being falsy.
        if (
            topic in remaining_num_topic_boosts
            and len(boosted_recs) < MAX_TOP_REC_SLOTS
            and remaining_num_topic_boosts.get(topic)
        ):
            boosted_recs.append(rec)
            remaining_num_topic_boosts[topic] -= 1  # decrement remaining # of topics to boost
        else:
            remaining_recs.append(rec)

    return boosted_recs + remaining_recs


def is_section_recently_followed(followed_at: datetime | None) -> bool:
    """Check if a section was followed within the last 7 days. Use UTC timezone.

    :param followed_at: the date a section was followed on
    :return: boolean
    """
    # If no timestamp provided, consider as not recently followed
    if not followed_at:
        return False

    # Return followed_at in UTC timezone (in case client sent in different timezone)
    followed_at = followed_at.astimezone(timezone.utc)

    # Get current UTC time
    current_time = datetime.now(timezone.utc)

    # Return true if recently followed (<=7) false if > 7
    return current_time - followed_at <= timedelta(days=7)


def section_boosting_composite_sorting_key(section):
    """Return a composite sort key for boosting sections.

    - 1st sort order: Followed sections get higher rank
    - 2nd sort order: Recently followed sections get a higher rank among followed sections
    - 3rd sort order: Most recent sections among recently followed sections get a higher rank
    - 4th sort order: Unfollowed / blocked sections are pushed to the very end, relative order is preserved
    """
    section_followed = section.isFollowed
    section_recent = is_section_recently_followed(section.followedAt)
    section_followed_at = section.followedAt.timestamp() if section.followedAt else 0
    existing_rank = section.receivedFeedRank or 0

    return (
        0 if section_followed else 1,  # 1st sort order
        0 if section_recent else 1,  # 2nd sort order
        -section_followed_at,  # 3rd sort order
        existing_rank,  # 4th sort order
    )


def boost_followed_sections(
    req_sections: list[SectionConfiguration], sections: dict[str, Section]
) -> dict[str, Section]:
    """Boost followed sections to the very top and update receivedFeedRank accordingly.
    Most recently followed sections (followed within 1 week) should be boosted higher.
    Unfollowed sections should be ranked after followed_sections, and relative order should be preserved.

    :param req_sections: List of Section configurations
    :param sections: Dictionary with section ids as keys and Section objects as values.
    :return: Updated dictionary with boosted followed sections (if found)
    """
    # 1. Extract section ids from the section request
    initial_section_ids = [section.sectionId for section in req_sections]

    # 2. Extract followed section ids & followedAt from req_sections param & store in a dict for quick lookup
    followed_sections_info = {
        section.sectionId: section.followedAt for section in req_sections if section.isFollowed
    }

    # 3. Extract blocked section ids from req_sections param
    blocked_section_ids = {section.sectionId for section in req_sections if section.isBlocked}

    # 4. Update section attributes for sections in the request
    for section_id in initial_section_ids:
        # lookup the section using the SERP topic from client
        section = sections.get(section_id)
        if not section:
            continue  # skip sections that did not map

        # set follow attributes if section is followed
        if section_id in followed_sections_info:
            section.isFollowed = True
            section.followedAt = followed_sections_info[section_id]
        # if section is blocked, set isBlocked
        if section_id in blocked_section_ids:
            section.isBlocked = True

    # 5. Sort the sections using lambda composite key
    sorted_sections = sorted(sections.values(), key=section_boosting_composite_sorting_key)

    # 6. Assign new rank starting from 0 for the sorted sections
    for new_rank, section in enumerate(sorted_sections):
        section.receivedFeedRank = new_rank

    return sections
