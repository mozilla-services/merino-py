"""Algorithms for ranking curated recommendations."""

import logging

from random import sample as random_sample

from merino.curated_recommendations.engagement_backends.protocol import EngagementBackend
from merino.curated_recommendations.prior_backends.constant_prior import ConstantPrior
from merino.curated_recommendations.prior_backends.protocol import (
    EngagementRescaler,
    Prior,
    PriorBackend,
)
from merino.curated_recommendations.protocol import (
    CuratedRecommendation,
    ProcessedInterests,
    Section,
)
from merino.curated_recommendations.rankers.utils import REGION_ENGAGEMENT_WEIGHT

logger = logging.getLogger(__name__)


class Ranker:
    """Base class for ranking curated recommendations"""

    def __init__(
        self,
        engagement_backend: EngagementBackend,
        prior_backend: PriorBackend,
        region_weight: float = REGION_ENGAGEMENT_WEIGHT,
    ) -> None:
        self.engagement_backend = engagement_backend
        self.prior_backend = prior_backend
        self.region_weight = region_weight

    def get_opens_no_opens(
        self, rec: CuratedRecommendation, region_query: str | None = None
    ) -> tuple[float, float]:
        """Get opens and no-opens counts for a recommendation, optionally in a region."""
        engagement = self.engagement_backend.get(rec.corpusItemId, region_query)
        if engagement:
            return engagement.click_count, engagement.impression_count - engagement.click_count
        else:
            return 0, 0

    def compute_interactions(
        self,
        rec: CuratedRecommendation,
        rescaler: EngagementRescaler | None = None,
        region: str | None = None,
    ) -> tuple[float, float, float, float, float]:
        """Compute opens, no_opens, a_prior, b_prior, non_rescaled_b_prior for a recommendation."""
        opens, no_opens = self.get_opens_no_opens(rec)
        region_opens, region_no_opens = self.get_opens_no_opens(rec, region_query=region)

        prior: Prior = self.prior_backend.get() or ConstantPrior().get()
        a_prior = float(prior.alpha)
        b_prior = float(prior.beta)
        region_prior = self.prior_backend.get(region)

        if region_no_opens and region_prior:
            # Weighted average of regional and global engagement
            opens = region_opens * self.region_weight + opens * (1 - self.region_weight)
            no_opens = region_no_opens * self.region_weight + no_opens * (1 - self.region_weight)
            a_prior = (self.region_weight * region_prior.alpha) + (
                (1 - self.region_weight) * a_prior
            )
            b_prior = (self.region_weight * region_prior.beta) + (
                (1 - self.region_weight) * b_prior
            )

        if rescaler is not None:
            opens, no_opens = rescaler.rescale(rec, opens, no_opens)

        non_rescaled_b_prior = b_prior
        if rescaler is not None:
            a_prior, b_prior = rescaler.rescale_prior(rec, a_prior, b_prior)

        return opens, no_opens, a_prior, b_prior, non_rescaled_b_prior

    def suppress_fresh_items(
        self, scored_recs: list[CuratedRecommendation], fresh_items_max: int
    ) -> None:
        """Reduce the scores of fresh items if there are too many."""
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

    def rank_items(
        self,
        recs: list[CuratedRecommendation],
        rescaler: EngagementRescaler | None = None,
        personal_interests: ProcessedInterests | None = None,
        utcOffset: int | None = None,
        region: str | None = None,
    ) -> list[CuratedRecommendation]:
        """Rank items according to some criteria."""
        # Placeholder implementation: sort by title alphabetically
        return recs

    def rank_sections(
        self,
        sections: dict[str, Section],
        top_n: int = 6,
        rescaler: EngagementRescaler | None = None,
    ) -> dict[str, Section]:
        """Rank sections."""
        return sections
