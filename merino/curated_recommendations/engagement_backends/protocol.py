"""Protocol and Pydantic models for the Engagement provider backend."""

from typing import Protocol
from pydantic import BaseModel


class Engagement(BaseModel):
    """Represents the engagement data from the last 24 hours for a scheduled corpus item.

    Engagement is aggregated over a rolling 24-hour window by scheduled_corpus_item_id, a unique ID
     for the URL, scheduled date, and surface (e.g., "New Tab en-US"). It's expected to be updated
     periodically with a delay of < 30 minutes from when clicks or impressions happen in the client.
    """

    scheduled_corpus_item_id: str
    click_count: int
    impression_count: int


class EngagementBackend(Protocol):
    """Protocol for Engagement backend that the provider depends on."""

    def get(self, scheduled_corpus_item_id: str) -> Engagement | None:
        """Fetch engagement data for the given scheduled corpus item id"""
        ...

    def initialize(self) -> None:
        """Start any background jobs"""
        ...
