"""Module dedicated to ML Recs that returns an empty set of recommnendations"""

import logging

from merino.curated_recommendations.ml_backends.protocol import (
    MLRecsBackend,
    ContextualArticleRankings,
)

logger = logging.getLogger(__name__)


class EmptyMLRecs(MLRecsBackend):
    """Backend that fetches ML Recs from GCS for Contextual Ranker"""

    def get(
        self,
        region: str | None = None,
        utc_offset: str | None = None,
    ) -> ContextualArticleRankings | None:
        """Get empty recommendations that should be handled downstream if this happens

        Args:
            region: The region for which to return prior data (e.g. 'US').
            utc_offset: The UTC offset for which to return the ranked articles

        Returns:
            ContextualArticleRankings: Ranked articles for a given region and utc offset with seeds
        """
        return None
