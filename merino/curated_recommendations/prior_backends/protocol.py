"""Protocol and Pydantic models for the Thompson sampling prior backend."""

from typing import Protocol, Any
from pydantic import BaseModel

from merino.curated_recommendations.protocol import CuratedRecommendation


class Prior(BaseModel):
    """Represents the Thompson sampling prior data for a specific region."""

    region: str | None = None
    alpha: float
    beta: float


class PriorBackend(Protocol):
    """Protocol for Thompson Sampling Prior backend that the provider depends on."""

    def get(self, region: str | None = None) -> Prior | None:
        """Fetch Thompson sampling prior data for the given region.

        Args:
            region: Optionally, the region for which to return prior data (e.g. 'US'). If region is
              None, then a global prior will be returned.

        Returns:
            Prior: Thompson sampling prior for the given region, or None if prior is unavailable.
        """
        ...

    @property
    def update_count(self) -> int:
        """Return the number of times the prior data has been updated."""
        ...


class ExperimentRescaler(BaseModel):
    """Used to scale priors based on relative experiment size, when an experiment
    include content that is not in other test branches.

    Also contains parameters for limiting the number of unscored items in most popular
    """

    fresh_items_limit_prior_threshold_multiplier: float = (
        0  # mult * prior limit to determine whether item is fresh
    )
    fresh_items_max: (
        int  # Max number of fresh items highly ranked fresh items. Affects section ranking indirectly.
        # This can be kept higher than desired because top_stories_max_percentage acts as a guard
    ) = 0
    fresh_items_top_stories_max_percentage: (
        float  # Max number of fresh percentage of items in top stories
    ) = 0

    def __init__(self, **data: Any):
        super().__init__(**data)

    def rescale(self, rec: CuratedRecommendation, opens, no_opens):
        """Update open and non-open values based on whether item is unique to the experiment. Note that
        impressions and clicks can be used in place of opens and no_opens
        """
        return opens, no_opens

    def rescale_prior(self, rec: CuratedRecommendation, alpha, beta):
        """Update priors values based on whether item is unique to the experiment."""
        return alpha, beta
