"""Protocol for the AdM provider backends."""

from enum import Enum
from typing import Optional, Protocol

from pydantic import BaseModel, ConfigDict, model_validator
from moz_merino_ext.amp import AmpIndexManager

SegmentType = tuple[int]
IndexType = dict[str, dict[SegmentType, tuple[int, int]]]


class FormFactor(Enum):
    """Enum for form factor."""

    DESKTOP = 0
    PHONE = 1


class KeywordMetrics(BaseModel):
    """Impressions and clicks for a single time window."""

    impressions: int
    clicks: int


class KeywordEntry(BaseModel):
    """Live and historical engagement metrics for a single advertiser/keyword pair."""

    live: Optional[KeywordMetrics] = None
    historical: Optional[KeywordMetrics] = None

    @model_validator(mode="after")
    def at_least_one_present(self) -> "KeywordEntry":
        """Check that there is at least one type of metrics set."""
        if self.live is None and self.historical is None:
            raise ValueError("at least one of live or historical must be set")
        return self


class EngagementData(BaseModel):
    """Model for keyword-level engagement data file content."""

    amp: dict[str, KeywordEntry] = {}
    amp_aggregated: dict[str, int] = {}


class SuggestionContent(BaseModel):
    """Class that holds the result from a fetch operation."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    index_manager: AmpIndexManager

    # A dictionary of icon IDs to icon URLs.
    icons: dict[str, str]


class AdmBackend(Protocol):
    """Protocol for an AdM backend that this provider depends on.

    Note: This only defines the methods used by the provider. The actual backend
    might define additional methods and attributes which this provider doesn't
    directly depend on.
    """

    async def fetch(self) -> SuggestionContent:  # pragma: no cover
        """Get suggestion content from partner."""
        ...
