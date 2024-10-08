"""A fake implementation of EngagementBackend that's used when GCS credentials are unavailable."""

from merino.curated_recommendations.engagement_backends.protocol import (
    Engagement,
    EngagementBackend,
)


class FakeEngagement(EngagementBackend):
    """Fallback backend that returns None for any engagement data."""

    def get(self, scheduled_corpus_item_id: str, region: str | None = None) -> Engagement | None:
        """No-op for getting engagement data."""
        return None

    def initialize(self) -> None:
        """No-op for fake backend initialization."""
        pass

    @property
    def update_count(self) -> int:
        """Return the number of times the engagement has been updated."""
        return 0
