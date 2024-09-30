"""Algorithms for ranking curated recommendations."""

from copy import copy

from merino.curated_recommendations.corpus_backends.protocol import Topic
from merino.curated_recommendations.engagement_backends.protocol import EngagementBackend
from merino.curated_recommendations.protocol import CuratedRecommendation
from scipy.stats import beta

DEFAULT_ALPHA_PRIOR = 188  # beta * P99 German NewTab CTR for 2023-03-28 to 2023-04-05 (1.5%)
DEFAULT_BETA_PRIOR = (
    12500  # 0.5% of median German NewTab item impressions for 2023-03-28 to 2023-04-05.
)
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
    alpha_prior: float = DEFAULT_ALPHA_PRIOR,
    beta_prior: float = DEFAULT_BETA_PRIOR,
    enable_region_engagement: bool = False,
    region: str | None = None,
    region_weight: float = REGION_ENGAGEMENT_WEIGHT,
) -> list[CuratedRecommendation]:
    """Re-rank items using [Thompson sampling][thompson-sampling], combining exploitation of known item
    CTR with exploration of new items using a prior.

    :param recs: A list of recommendations in the desired order (pre-publisher spread).
    :param engagement_backend: Provides aggregate click and impression engagement by scheduledCorpusItemId.
    :param alpha_prior: Prior successes (e.g., clicks). Must be > 0.
    :param beta_prior: Prior failures (e.g., non-click impressions). Must be > 0.
    :param enable_region_engagement: If True, regional engagement weighs higher. False by default.
    :param region: Optionally, the client's region, e.g. 'US'.
    :param region_weight: In a weighted average, how much to weigh regional engagement.

    :return: A re-ordered version of recs, ranked according to the Thompson sampling score.

    [thompson-sampling]: https://en.wikipedia.org/wiki/Thompson_sampling
    """

    def get_opens_no_opens(
        rec: CuratedRecommendation, region_query: str | None = None
    ) -> tuple[float, float]:
        """Get opens and no-opens counts for a recommendation, optionally in a region."""
        engagement = engagement_backend.get(rec.scheduledCorpusItemId, region_query)
        if engagement:
            return engagement.click_count, engagement.impression_count - engagement.click_count
        else:
            return 0, 0

    def sample_score(rec: CuratedRecommendation) -> float:
        """Sample beta distributed from weighted regional/global engagement for a recommendation."""
        opens, no_opens = get_opens_no_opens(rec)

        # Use a weighted average of regional and global engagement, if that's enabled and available.
        if enable_region_engagement:
            region_opens, region_no_opens = get_opens_no_opens(rec, region)
            if region_no_opens:
                opens = (region_weight * region_opens) + ((1 - region_weight) * opens)
                no_opens = (region_weight * region_no_opens) + ((1 - region_weight) * no_opens)

        opens += alpha_prior
        no_opens += beta_prior

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
