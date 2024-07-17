"""Protocol and Pydantic models for the Engagement provider backend."""

from typing import Protocol
from pydantic import BaseModel


class Engagement(BaseModel):
    """Represents the engagement data for a scheduled corpus item."""

    scheduled_corpus_item_id: str
    clicks: int
    impressions: int


class EngagementBackend(Protocol):
    """Protocol for Engagement backend that the provider depends on."""

    def __getitem__(self, scheduled_corpus_item_id: str) -> Engagement:
        """Fetch engagement data for the given scheduled corpus item id"""
        ...

    def shutdown(self) -> None:
        """Clean up any resources"""
        ...
