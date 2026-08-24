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
        prior_alpha_multiplier: float = 1.0,
    ) -> None:
        self.engagement_backend = engagement_backend
        self.prior_backend = prior_backend
        self.region_weight = region_weight
        self.prior_alpha_multiplier = prior_alpha_multiplier

    def get_opens_no_opens(
        self, rec: CuratedRecommendation, region_query: str | None = None
    ) -> tuple[float, float, bool]:
        """Get opens, no-opens, and whether engagement exists for a recommendation."""
        engagement = self.engagement_backend.get(rec.corpusItemId, region_query)
        if engagement:
            return (
                engagement.click_count,
                engagement.impression_count - engagement.click_count,
                True,
            )
        else:
            return 0, 0, False

    def resolve_engagement_region(
        self,
        recs: list[CuratedRecommendation],
        region: str | None = None,
        engagement_region: str | None = None,
    ) -> str | None:
        """Return the engagement region to use for the full candidate list.

        Branch-specific engagement regions should be all-or-nothing for a ranking pass:
        use the branch region if any candidate has branch engagement, otherwise fall back
        to the base country region.
        """
        if engagement_region is None or engagement_region == region:
            return engagement_region

        for rec in recs:
            if self.engagement_backend.get(rec.corpusItemId, engagement_region) is not None:
                return engagement_region

        return region

    def get_regional_prior(
        self,
        region: str | None = None,
        prior_region: str | None = None,
    ) -> Prior | None:
        """Return the prior for a branch region, falling back to the base region.

        Branch-specific priors are request-level artifacts. If a branch prior exists,
        use it for the full ranking pass; otherwise fall back to the base country prior.
        """
        if prior_region is not None and prior_region != region:
            prior = self.prior_backend.get(prior_region)
            if prior is not None:
                return prior

        return self.prior_backend.get(region)

    def compute_interactions(
        self,
        rec: CuratedRecommendation,
        rescaler: EngagementRescaler | None = None,
        region: str | None = None,
        engagement_region: str | None = None,
        regional_prior: Prior | None = None,
        blend_region_with_global=True,
    ) -> tuple[float, float, float, float, float]:
        """Compute opens, no_opens, a_prior, b_prior, non_rescaled_b_prior for a recommendation."""
        opens, no_opens, _ = self.get_opens_no_opens(rec)
        region_query = engagement_region if engagement_region is not None else region
        region_opens, region_no_opens, _ = self.get_opens_no_opens(rec, region_query=region_query)

        prior: Prior = self.prior_backend.get() or ConstantPrior().get()
        a_prior = float(prior.alpha)
        b_prior = float(prior.beta)
        region_prior = (
            regional_prior if regional_prior is not None else self.prior_backend.get(region)
        )

        if region_no_opens and region_prior:
            # Weighted average of regional and global engagement
            region_weight = self.region_weight if blend_region_with_global else 1.0
            opens = region_opens * region_weight + opens * (1 - region_weight)
            no_opens = region_no_opens * region_weight + no_opens * (1 - region_weight)
            a_prior = (region_weight * region_prior.alpha) + ((1 - region_weight) * a_prior)
            b_prior = (region_weight * region_prior.beta) + ((1 - region_weight) * b_prior)

        a_prior *= self.prior_alpha_multiplier

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
        region: str | None = None,
        engagement_region: str | None = None,
    ) -> list[CuratedRecommendation]:
        """Rank items according to some criteria."""
        # Placeholder implementation: sort by title alphabetically
        return recs

    def rank_sections(
        self,
        sections: dict[str, Section],
        top_n: int = 4,
        rescaler: EngagementRescaler | None = None,
        region: str | None = None,
        engagement_region: str | None = None,
    ) -> dict[str, Section]:
        """Rank sections."""
        return sections
