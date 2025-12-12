"""Algorithms for ranking curated recommendations."""

import logging

from merino.curated_recommendations import ConstantPrior
from merino.curated_recommendations.ml_backends.static_local_model import DEFAULT_INTERESTS_KEY
from merino.curated_recommendations.prior_backends.protocol import (
    EngagementRescaler,
)
from merino.curated_recommendations.protocol import (
    CuratedRecommendation,
    Section,
    ProcessedInterests,
    RankingData,
)
from scipy.stats import beta

from merino.curated_recommendations.rankers.ranker import Ranker
from merino.curated_recommendations.rankers.utils import (
    INFERRED_SCORE_WEIGHT,
    filter_fresh_items_with_probability,
    renumber_sections,
)

logger = logging.getLogger(__name__)


class ThompsonSamplingRanker(Ranker):
    """Base class for ranking curated recommendations"""

    def rank_items(
        self,
        recs: list[CuratedRecommendation],
        rescaler: EngagementRescaler | None = None,
        personal_interests: ProcessedInterests | None = None,
        utcOffset: int | None = None,
        region: str | None = None,
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
        fresh_items_max: int = rescaler.fresh_items_max if rescaler else 0
        fresh_items_limit_prior_threshold_multiplier: float = (
            rescaler.fresh_items_limit_prior_threshold_multiplier if rescaler else 0
        )

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
            opens, no_opens, a_prior, b_prior, non_rescaled_b_prior = self.compute_interactions(
                rec, rescaler, region
            )
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
                and (
                    no_opens < non_rescaled_b_prior * fresh_items_limit_prior_threshold_multiplier
                )
            ):
                rec.ranking_data.is_fresh = True

        for rec in recs:
            compute_ranking_scores(rec)
        self.suppress_fresh_items(recs, fresh_items_max)
        # Sort the recommendations from best to worst sampled score & renumber
        sorted_recs = sorted(
            recs,
            key=lambda r: r.ranking_data.score if r.ranking_data is not None else float("-inf"),
            reverse=True,
        )
        return sorted_recs

    def rank_sections(
        self,
        sections: dict[str, Section],
        top_n: int = 6,
        rescaler: EngagementRescaler | None = None,
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

            fresh_retain_likelyhood = (
                rescaler.fresh_items_section_ranking_max_percentage
                if rescaler is not None
                else 0.0
            )
            recs, _ = filter_fresh_items_with_probability(
                sec.recommendations, fresh_story_prob=fresh_retain_likelyhood, max_items=top_n
            )

            total_clicks = 0.0
            total_imps = 0.0
            a_prior_total = 0.0
            b_prior_total = 0.0

            # Note that we are using the constant prior here, which is likely a bug.
            # This should be transitioned to use the results of compute_interactions function below
            prior = ConstantPrior().get()

            for rec in recs:
                opens, no_opens, a_prior, b_prior, non_rescaled_b_prior = (
                    self.compute_interactions(rec, rescaler, "??")
                )
                total_clicks += opens
                total_imps += no_opens

                a_prior_per_item = float(prior.alpha)
                b_prior_per_item = float(prior.beta)
                if rescaler is not None:
                    a_prior_per_item, b_prior_per_item = rescaler.rescale_prior(
                        rec, a_prior_per_item, b_prior_per_item
                    )

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
