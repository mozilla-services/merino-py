"""Algorithms for ranking curated recommendations."""

from random import randint, random

from merino.curated_recommendations.ml_backends.protocol import (
    ContextualArticleRankings,
    MLRecsBackend,
)
import logging

from merino.curated_recommendations.engagement_backends.protocol import EngagementBackend
from merino.curated_recommendations.prior_backends.protocol import (
    PriorBackend,
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
    REGION_ENGAGEMENT_WEIGHT,
    filter_fresh_items_with_probability,
    renumber_sections,
)

# We are still learning how to compute how many impressions before we can trust the ranker score completely
# So far, 4000 impressions seems to be a reasonable average beta value to use as a threshold
# This means that items with less than 4000 impressions will be marked as fresh.
CONTEXUAL_AVG_BETA_VALUE = 4000
CONTEXTAL_LIMIT_PERCENTAGE_ADJUSTMENT = (
    0.5  # Underscored items tend to scale higher, leading to too much fresh content
)

logger = logging.getLogger(__name__)


class ContextualRanker(Ranker):
    """Base class for ranking curated recommendations"""

    def __init__(
        self,
        engagement_backend: EngagementBackend,
        prior_backend: PriorBackend,
        region_weight: float = REGION_ENGAGEMENT_WEIGHT,
        ml_backend: MLRecsBackend | None = None,
        disable_time_zone_context: bool = False,
    ) -> None:
        super().__init__(engagement_backend, prior_backend, region_weight)
        assert ml_backend is not None
        self.ml_backend: MLRecsBackend = ml_backend
        self.disable_time_zone_context = disable_time_zone_context

    def rank_items(
        self,
        recs: list[CuratedRecommendation],
        rescaler: EngagementRescaler | None = None,
        personal_interests: ProcessedInterests | None = None,
        utcOffset: int | None = None,
        region: str | None = None,
    ) -> list[CuratedRecommendation]:
        """Pull out scores that were previously computed from the contextual ranker
        data artifact. We need to look up the items in the ml backend using region and utcOffset.
        """
        fresh_items_limit_prior_threshold_multiplier: float = (
            rescaler.fresh_items_limit_prior_threshold_multiplier if rescaler else 0
        )

        cohort = None
        if personal_interests is not None:
            cohort = personal_interests.cohort
        if self.disable_time_zone_context:
            utcOffset = None
        contextual_scores: ContextualArticleRankings | None = self.ml_backend.get(
            region, str(utcOffset), cohort
        )
        k = randint(0, contextual_scores.K - 1) if contextual_scores is not None else 0
        for rec in recs:
            opens, no_opens, a_prior, b_prior, non_rescaled_b_prior = self.compute_interactions(
                rec, rescaler, region
            )
            is_fresh = False
            # add random value between 0 and 1 to break ties randomly
            score = None
            if contextual_scores:
                score = contextual_scores.get_score(rec.corpusItemId, k)

            beta_value_for_fresh_check = non_rescaled_b_prior

            if score is None:
                # Fall back to Thompson sampling if no ML score is found because no data has come in yet
                alpha_val = opens + max(a_prior, 1e-18)
                beta_val = no_opens + max(b_prior, 1e-18)
                score = float(beta.rvs(alpha_val, beta_val))
            else:
                # Contextual ranker known imprssions override the computed no_opens based on engagement
                # which runs on a different interval. We will need to potentially rescale the ml_backend
                # impresions before completely ignoring the no_opens from the legacy engagement backend.
                no_opens = self.ml_backend.get_adjusted_impressions(rec.corpusItemId)
                score += random() * 0.0001
                beta_value_for_fresh_check = CONTEXUAL_AVG_BETA_VALUE
            if (
                (fresh_items_limit_prior_threshold_multiplier > 0)
                and not rec.isTimeSensitive
                and (
                    no_opens
                    < beta_value_for_fresh_check * fresh_items_limit_prior_threshold_multiplier
                )
            ):
                is_fresh = True

            rec.ranking_data = RankingData(
                score=score,
                alpha=0,
                beta=0,
                is_fresh=is_fresh,
            )

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
        """Re-rank sections using average score of top items."""

        def sample_score(sec: Section) -> float:
            """Create score based on top items in section"""
            fresh_retain_likelyhood = (
                rescaler.fresh_items_section_ranking_max_percentage
                * CONTEXTAL_LIMIT_PERCENTAGE_ADJUSTMENT
                if rescaler is not None
                else 0.0
            )
            recs, _ = filter_fresh_items_with_probability(
                sec.recommendations, fresh_story_prob=fresh_retain_likelyhood, max_items=top_n
            )
            total_score = 0.0
            n_scores = 0
            for rec in recs:
                if rec.ranking_data:
                    total_score += rec.ranking_data.score
                    n_scores += 1

            return total_score / n_scores if n_scores > 0 else 0.0

        ordered = sorted(sections.items(), key=lambda kv: sample_score(kv[1]), reverse=True)
        return renumber_sections(ordered)
