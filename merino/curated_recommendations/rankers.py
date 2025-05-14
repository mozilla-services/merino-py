"""Algorithms for ranking curated recommendations."""

from copy import copy
from datetime import datetime, timedelta, timezone

from merino.curated_recommendations import ConstantPrior
from merino.curated_recommendations.corpus_backends.protocol import Topic
from merino.curated_recommendations.engagement_backends.protocol import EngagementBackend
from merino.curated_recommendations.prior_backends.protocol import PriorBackend, Prior
from merino.curated_recommendations.protocol import (
    CuratedRecommendation,
    SectionConfiguration,
    Section,
)
from scipy.stats import beta


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


def thompson_sampling(
    recs: list[CuratedRecommendation],
    engagement_backend: EngagementBackend,
    prior_backend: PriorBackend,
    region: str | None = None,
    region_weight: float = REGION_ENGAGEMENT_WEIGHT,
) -> list[CuratedRecommendation]:
    """Re-rank items using [Thompson sampling][thompson-sampling], combining exploitation of known item
    CTR with exploration of new items using a prior.

    :param recs: A list of recommendations in the desired order (pre-publisher spread).
    :param engagement_backend: Provides aggregate click and impression engagement by corpusItemId.
    :param prior_backend: Provides prior alpha and beta values for Thompson sampling.
    :param region: Optionally, the client's region, e.g. 'US'.
    :param region_weight: In a weighted average, how much to weigh regional engagement.

    :return: A re-ordered version of recs, ranked according to the Thompson sampling score.

    [thompson-sampling]: https://en.wikipedia.org/wiki/Thompson_sampling
    """
    fallback_prior = ConstantPrior().get()

    def get_opens_no_opens(
        rec: CuratedRecommendation, region_query: str | None = None
    ) -> tuple[float, float]:
        """Get opens and no-opens counts for a recommendation, optionally in a region."""
        engagement = engagement_backend.get(rec.corpusItemId, region_query)
        if engagement:
            return engagement.click_count, engagement.impression_count - engagement.click_count
        else:
            return 0, 0

    def sample_score(rec: CuratedRecommendation) -> float:
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

        # Add priors and ensure opens and no_opens are > 0, which is required by beta.rvs.
        opens += max(a_prior, 1e-18)
        no_opens += max(b_prior, 1e-18)

        return float(beta.rvs(opens, no_opens))

    # Sort the recommendations from best to worst sampled score.
    return sorted(recs, key=sample_score, reverse=True)


def section_thompson_sampling(
    sections: dict[str, Section],
    engagement_backend: EngagementBackend,
    top_n: int = 6,
) -> dict[str, Section]:
    """Re-rank sections using [Thompson sampling][thompson-sampling], based on the combined engagement of top items.

    :param sections: Mapping of section IDs to Section objects whose recommendations will be scored.
    :param engagement_backend: Provides aggregate click and impression engagement by corpusItemId.
    :param top_n: Number of top items in each section for which to sum engagement in the Thompson sampling score.

    :return: Mapping of section IDs to Section objects with updated receivedFeedRank.

    [thompson-sampling]: https://en.wikipedia.org/wiki/Thompson_sampling
    """

    def sample_score(sec: Section) -> float:
        """Sample beta distribution for the combined engagement of the top _n_ items."""
        # sum clicks and impressions over top_n items
        recs = sec.recommendations[:top_n]
        total_clicks = 0
        total_imps = 0
        for rec in recs:
            if engagement := engagement_backend.get(rec.corpusItemId):
                total_clicks += engagement.click_count
                total_imps += engagement.impression_count

        # constant prior α, β
        prior = ConstantPrior().get()
        a_prior = top_n * prior.alpha
        b_prior = top_n * prior.beta

        # Sum engagement and priors.
        opens = total_clicks + a_prior
        no_opens = total_imps - total_clicks + b_prior

        # Sample distribution
        return float(beta.rvs(opens, no_opens))

    # sort sections by sampled score, highest first
    ordered = sorted(sections.items(), key=lambda kv: sample_score(kv[1]), reverse=True)
    return renumber_sections(ordered)

def aggregate_section_click_passes(
    sections: dict[str, Section],
    engagement_backend: EngagementBackend,    
) -> dict[str, Section]:
    """Aggregate item clicks and impressions to section level clicks and passes

    :param sections: Mapping of section IDs to Section objects whose recommendations will be scored.
    :param engagement_backend: Provides aggregate click and impression engagement by corpusItemId.    

    :return: Mapping of section IDs to Section objects with updated clicks and passes
    """

    def aggregate_counts(sec: Section) -> float:
        """cycle articles and aggregate section clicks and passes"""
        # sum clicks and impressions over all items
        recs = sec.recommendations
        total_clicks = 0
        total_imps = 0
        for rec in recs:
            if engagement := engagement_backend.get(rec.corpusItemId):
                total_clicks += engagement.click_count
                total_imps += engagement.impression_count

        # Sum engagement and priors.
        opens = total_clicks 
        no_opens = total_imps - total_clicks 

        return opens, no_opens

    # update clicks and passes
    for k in sections:
        sections[k]['clicks'],sections[k]['passes'] = aggregate_counts(sections[k])
        
    return sections



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
    key = "top_stories_section"
    top_stories = sections.get(key)
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
