"""A fake implementation of FakespotBackend that's used when GCS credentials are unavailable."""

from merino.curated_recommendations.fakespot_backend.protocol import (
    FakespotFeed,
    FakespotBackend,
)


class FakeFakespotBackend(FakespotBackend):
    """Fallback backend that returns None for any fakespot products data."""

    def get(self, key: str) -> FakespotFeed | None:
        """No-op for getting fakespot products data."""
        return None

    def initialize(self) -> None:
        """No-op for fake backend initialization."""
        pass

    @property
    def update_count(self) -> int:
        """Return the number of times the fakespot products data has been updated."""
        return 0
