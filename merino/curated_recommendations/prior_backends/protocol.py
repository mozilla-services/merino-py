"""Protocol and Pydantic models for the Thompson sampling prior backend."""

from typing import Protocol
from pydantic import BaseModel


class Prior(BaseModel):
    """Represents the Thompson sampling prior data for a specific region."""

    region: str
    alpha_prior: float
    beta_prior: float


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
