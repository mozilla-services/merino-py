"""Module dedicated to ML Recs that returns an empty set of recommnendations"""

import logging

from merino.curated_recommendations.corpus_backends.protocol import SurfaceId
from merino.curated_recommendations.ml_backends.protocol import (
    MLRecsBackend,
    ContextualArticleRankings,
)

logger = logging.getLogger(__name__)


class EmptyMLRecs(MLRecsBackend):
    """Backend that fetches ML Recs from GCS for Contextual Ranker"""

    def get(
        self,
        surface_id: SurfaceId,
        region: str | None = None,
        cohort: str | None = None,
        time_zone: str | None = None,
    ) -> ContextualArticleRankings | None:
        """Get empty recommendations that should be handled downstream if this happens

        Args:
            surface_id: The surface for which to return rankings.
            region: The region for which to return prior data (e.g. 'US').
            cohort: The users cohort for which to return the ranked articles
            time_zone: The user's time zone Id ("0" for Pacific, "3" for Eastern, etc.)

        Returns:
            ContextualArticleRankings: Ranked articles for a given region and utc offset with seeds
        """
        return None

    def get_adjusted_impressions(self, corpus_item_id: str, surface_id: SurfaceId) -> int:
        """Return the impression count for a given corpus item id (adjusted for propensity)"""
        return 0

    def is_valid(self, surface_id: SurfaceId) -> bool:
        """Return whether the backend is valid and ready to serve recommendations. In this case, always false."""
        return False

    def get_cohort_training_run_id(self, surface_id: SurfaceId) -> str | None:
        """Return the training run ID for the cohort model used."""
        return None
