"""Algorithms for ranking curated recommendations."""

from copy import copy

from merino.curated_recommendations import ConstantPrior
from merino.curated_recommendations.corpus_backends.protocol import Topic
from merino.curated_recommendations.engagement_backends.protocol import EngagementBackend
from merino.curated_recommendations.prior_backends.protocol import PriorBackend, Prior
from merino.curated_recommendations.protocol import (
    CuratedRecommendation,
    CuratedRecommendationsFeed,
    SectionConfiguration,
)
from scipy.stats import beta

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


def boost_followed_sections(
    req_sections: list[SectionConfiguration], feeds: CuratedRecommendationsFeed
) -> CuratedRecommendationsFeed:
    """Boost followed sections to the very top, right after top_stories_section.
    Received feed rank for top_stories_section should always stay 0.
    Received feed rank for followed_sections should follow top_stories_section.
    Unfollowed sections should be ranked after followed_sections, and relative order should be preserved.

    :param req_sections: List of Section configurations
    :param feeds: CuratedRecommendationsFeed object
    :return: updated CuratedRecommendationsFeed with boosted followed sections (if found)
    """
    followed_sections = []
    unfollowed_sections = []

    # 1. Extract followed section ids from req_sections param
    followed_section_ids = [section.sectionId for section in req_sections if section.isFollowed]

    # 2. Extract blocked section ids from req_sections param
    blocked_section_ids = [section.sectionId for section in req_sections if section.isBlocked]

    # 3. Update isBlocked based on blocked_section_ids
    # For now, we will only update isBlocked value on a Section
    # The client-side will handle the actual blocking action
    if blocked_section_ids:
        for section_id in blocked_section_ids:
            section = feeds.get_section_by_topic_id(section_id)
            if section:
                section.isBlocked = True

    # 4. Update isFollowed based on followed_section_ids
    if followed_section_ids:
        for section_id in followed_section_ids:
            # lookup the followed section using the SERP topic from client
            section = feeds.get_section_by_topic_id(section_id)
            if section:
                section.isFollowed = True

        # 5. Collect followed & unfollowed sections
        for section_id in feeds.model_fields_set:
            section = getattr(feeds, section_id)
            if section:
                if section_id == "top_stories_section":
                    # top_stories_section is always on the top
                    section.receivedFeedRank = 0
                elif section.isFollowed:
                    followed_sections.append(section)
                else:
                    unfollowed_sections.append(section)

        # 6. Sort followed & unfollowed sections by their rank (ascending)
        # This is to ensure relative order is kept
        followed_sections.sort(key=lambda section: section.receivedFeedRank)
        unfollowed_sections.sort(key=lambda section: section.receivedFeedRank)

        # 7. Assign new rank starting from 1 for followed sections.
        current_received_feed_rank = 1
        for section in followed_sections:
            section.receivedFeedRank = current_received_feed_rank
            current_received_feed_rank += 1

        # 8. Assign new rank (starting from last rank value assigned to a followed section)
        # to unfollowed sections. Keep relative order.
        for section in unfollowed_sections:
            section.receivedFeedRank = current_received_feed_rank
            current_received_feed_rank += 1

    return feeds
