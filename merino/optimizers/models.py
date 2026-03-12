"""Shared models across optimizers"""

from typing import Any, Self

from pydantic import BaseModel, field_validator, model_validator, computed_field


class EngagementMetrics(BaseModel):
    """Model engagement metrics for optimizers."""

    # Total number of engaged activities. E.g. the click count for a suggestion.
    engaged: int

    # Total number of attempted activities. E.g. the impression count for a suggestion.
    attempted: int

    @field_validator("engaged", "attempted", mode="after")
    @classmethod
    def adjust(cls, value: int) -> int:
        """Adjust the counters to be no less than 1."""
        if value <= 0:
            return 1
        return value

    @model_validator(mode="after")
    def check(self) -> Self:
        """Check the counters."""
        if self.engaged > self.attempted:
            raise ValueError("`attempted` should be greater than or equal to `engaged`")
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def not_engaged(self) -> int:
        """Derive a property for not engaged activities adjusted to be no less than 1."""
        return max(self.attempted - self.engaged, 1)


class ThompsonConfig(BaseModel):
    """Model for Thompson sampling configuration."""

    # Minimal attempted count
    minimal_attempted_count: int = 0

    # Dummy candidate
    dummy_candidate: EngagementMetrics | None = None

    # Used (for testing) to set the seed to make random number generation reproducible.
    random_seed: int | None = None


class ThompsonCandidate(BaseModel):
    """Model for a candidate for the Thompson sampling optimizer."""

    # Candidate ID
    id: Any

    # Engagement metrics for this candidate
    metrics: EngagementMetrics
