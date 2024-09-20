"""Protocol and Pydantic models for the Engagement provider backend."""

from typing import Protocol
from pydantic import BaseModel


class Engagement(BaseModel):
    """Represents the engagement data from the last 24 hours for a scheduled corpus item.

    Engagement is aggregated over a rolling 24-hour window by scheduled_corpus_item_id, a unique ID
     for the URL, scheduled date, and surface (e.g., "New Tab en-US"). It's expected to be updated
     periodically with a delay of < 30 minutes from when clicks or impressions happen in the client.
    Additionally, engagement data is aggregated for the regions US, CA, IE, GB, DE, AU, and CH.
     If region is None this means engagement data is aggregated across all regions.
    """

    scheduled_corpus_item_id: str
    region: str | None = None  # If region is None, then engagement is across all regions.
    click_count: int
    impression_count: int


class EngagementBackend(Protocol):
    """Protocol for Engagement backend that the provider depends on."""

    def get(self, scheduled_corpus_item_id: str, region: str | None = None) -> Engagement | None:
        """Fetch engagement data for the given scheduled corpus item id and optionally region"""
        ...

    def initialize(self) -> None:
        """Start any background jobs"""
        ...

    @property
    def update_count(self) -> int:
        """Returns the number of times the engagement has been updated."""
        ...
