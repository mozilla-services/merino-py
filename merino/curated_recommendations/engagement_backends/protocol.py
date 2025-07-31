"""Protocol and Pydantic models for the Engagement provider backend."""
import logging
from typing import Protocol
from pydantic import BaseModel

logger = logging.getLogger(__name__)
class Engagement(BaseModel):
    """Represents the engagement data from the last 24 hours for a scheduled corpus item.

    Engagement is aggregated over a rolling 24-hour window by two different ids.
    - scheduled_corpus_item_id, a unique ID for the URL, scheduled date, and surface (New Tab en-US)
    - corpus_item_id, a unique ID only for the URL

    Initially, each item had a scheduled_corpus_item_id, but in 2025Q1 we will start recommending
    some items that only have a corpus_item_id.

    It's expected to be updated
     periodically with a delay of < 30 minutes from when clicks or impressions happen in the client.
    Additionally, engagement data is aggregated for the regions US, CA, IE, GB, DE, AU, and CH.
     If region is None this means engagement data is aggregated across all regions.
    """

    scheduled_corpus_item_id: str | None = None
    corpus_item_id: str | None = None  # Fx 135 started emitting corpus_item_id, so it may be null.
    region: str | None = None  # If region is None, then engagement is across all regions.
    click_count: int
    impression_count: int
    report_count: int | None = None

    def __add__(self, other):
        if not isinstance(other, Engagement):
            return NotImplemented
        if self.region != other.region:
            logger.error("Regions don't match adding engagements")
        if self.corpus_item_id != other.corpus_item_id:
            logger.error("corpus_item_id don't adding engagements")
        return Engagement(
            scheduled_corpus_item_id=self.scheduled_corpus_item_id or other.scheduled_corpus_item_id,
            corpus_item_id=self.corpus_item_id,
            region=self.region,
            click_count=self.click_count + other.click_count,
            impression_count=self.impression_count + other.impression_count,
            report_count=(self.report_count or 0) + (other.report_count or 0)
        )

class EngagementBackend(Protocol):
    """Protocol for Engagement backend that the provider depends on."""

    def get(self, corpus_item_id: str, region: str | None = None) -> Engagement | None:
        """Fetch engagement data for the given scheduled corpus item id and optionally region"""
        ...

    @property
    def update_count(self) -> int:
        """Returns the number of times the engagement has been updated."""
        ...
