"""Sport Data provided information"""

import logging

from abc import abstractmethod
from dynaconf import LazySettings
from pydantic import BaseModel, HttpUrl
from typing import Protocol

from merino.providers.suggest.base import (
    BaseSuggestion,
)

from merino.jobs.sportsdata_jobs import LOGGING_TAG
from merino.providers.manifest.backends.protocol import ManifestData


class SportsData(BaseModel):
    """Root result type for all Skeleton backends"""

    # Required fields for the Suggestion:
    # Who provided this result?
    provider: str = "SportsData info provider"
    # Where should the user go if they click on this?
    url: HttpUrl = HttpUrl(url="https://example.org")
    cache_dsn: str
    # What score should this result get when compared with other suggestions?
    score: float = 0.5

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def as_suggestion(self) -> BaseSuggestion:
        """Convert the result into a suggestion for publication"""
        ...


class SportsDataBackend(Protocol):
    """Root class for all SportsData backends"""

    manifest_data: ManifestData
    data: SportsData

    # The set of site metadata associated with this provider.
    # manifest_data: ManifestData

    def __init__(self, manifest_data: ManifestData, settings: LazySettings):
        # Connect to DataStore
        self.manifest_data = manifest_data
        self.data
