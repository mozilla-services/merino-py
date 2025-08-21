"""Example Suggest "live" provider"""

"""
We're extending the Merino FastAPI main, so there's a lot of configuration done elsewhere
"""

import logging

from abc import abstractmethod
from pydantic import BaseModel, HttpUrl
from typing import Protocol

from merino.providers.suggest.skeleton.backends.manifest import SkeletonManifest
from merino.providers.suggest.base import (
    BaseProvider,
    BaseSuggestion,
)


class SkeletonBackend(Protocol):
    """Root class for all Skeleton backends"""

    logger: logging.Logger
    # The set of site metadata associated with this provider.
    manifest_data: SkeletonManifest

    def __init__(self, manifest_data: SkeletonManifest):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.manifest_data = manifest_data


class SkeletonData(BaseModel):
    """Root result type for all Skeleton backends"""

    # Required fields for the Suggestion:
    # Who provided this result?
    provider: str = "Example Provider"
    # Where should the user go if they click on this?
    url: HttpUrl = HttpUrl(url="https://example.org")
    # What score should this result get when compared with other suggestions?
    score: float = 0.5

    @abstractmethod
    def as_suggestion(self) -> BaseSuggestion:
        """Convert the result into a suggestion for publication"""
        ...


class Provider(BaseProvider):
    """A Sample provider that returns an emoji based on a word or phrase"""

    backend: SkeletonBackend
