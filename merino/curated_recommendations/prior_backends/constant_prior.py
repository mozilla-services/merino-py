"""Module that provides a constant prior for Thompson sampling."""

from merino.curated_recommendations.prior_backends.protocol import Prior, PriorBackend


class ConstantPrior(PriorBackend):
    """Backend that provides a constant prior for Thompson sampling."""

    def get(self, region: str | None = None) -> Prior:
        """Get a constant Thompson sampling prior.

        Args:
            region: The region for which to return prior data (ignored in this implementation).

        Returns:
            Prior: A constant Thompson sampling prior.
        """
        return Prior(
            alpha=188,  # beta * P99 German NewTab CTR for 2023-03-28 to 2023-04-05 (1.5%)
            beta=12500,  # 0.5% of median German NewTab item impressions for 2023-03-28 to 2023-04-05
        )

    @property
    def update_count(self) -> int:
        """Return the number of times the prior data has been updated (always 0 for constant prior)."""
        return 0
