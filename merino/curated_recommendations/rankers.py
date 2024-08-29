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

MAX_TOP_REC_SLOTS = 10
NUM_RECS_PER_TOPIC = 2


class Rankers:
    @staticmethod
    def thompson_sampling(
            recs: list[CuratedRecommendation],
            engagement_backend: EngagementBackend,
            alpha_prior=DEFAULT_ALPHA_PRIOR,
            beta_prior=DEFAULT_BETA_PRIOR,
    ) -> list[CuratedRecommendation]:
        """Re-rank items using [Thompson sampling][thompson-sampling], combining exploitation of known item
        CTR with exploration of new items using a prior.

        :param recs: A list of recommendations in the desired order (pre-publisher spread).
        :param engagement_backend: Provides aggregate click and impression engagement by scheduledCorpusItemId.
        :param alpha_prior: Prior successes (e.g., clicks). Must be > 0.
        :param beta_prior: Prior failures (e.g., non-click impressions). Must be > 0.

        :return: A re-ordered version of recs, ranked according to the Thompson sampling score.

        [thompson-sampling]: https://en.wikipedia.org/wiki/Thompson_sampling
        """

        def get_score(rec: CuratedRecommendation) -> float:
            opens = alpha_prior
            no_opens = beta_prior

            engagement = engagement_backend.get(rec.scheduledCorpusItemId)
            if engagement:
                opens += engagement.click_count
                no_opens += engagement.impression_count - engagement.click_count

            return float(beta.rvs(opens, no_opens))

        return sorted(recs, key=get_score, reverse=True)

    @staticmethod
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

    @staticmethod
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
        boosted_recs = []
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
                    and len(remaining_num_topic_boosts) < MAX_TOP_REC_SLOTS
                    and remaining_num_topic_boosts[topic] > 0
            ):
                boosted_recs.append(rec)
                remaining_num_topic_boosts[topic] -= 1  # decrement remaining # of topics to boost
            else:
                remaining_recs.append(rec)

        return boosted_recs + remaining_recs
