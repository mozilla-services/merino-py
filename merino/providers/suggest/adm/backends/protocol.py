"""Protocol for the AdM provider backends."""

from typing import Protocol

from pydantic import BaseModel, ConfigDict
from moz_merino_ext.amp import AmpIndexManager

SegmentType = tuple[int]
IndexType = dict[str, dict[SegmentType, tuple[int, int]]]


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
