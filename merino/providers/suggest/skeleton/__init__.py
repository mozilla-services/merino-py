"""Example Suggest "live" provider

We're extending the Merino FastAPI main, so there's a lot of configuration done elsewhere

"""

import logging

from abc import abstractmethod
from pydantic import BaseModel, HttpUrl
from typing import Protocol

from merino.providers.suggest.base import (
    BaseSuggestion,
)

from merino.providers.manifest.backends.protocol import ManifestData

# The base suggestion score for this provider expressed as a float value
# ranging from 0.0 to 1.0.
BASE_SUGGEST_SCORE = 0.1


class SkeletonData(BaseModel):
    """Root result type for all Skeleton backends"""

    # Required fields for the Suggestion:
    # Who provided this result?
    provider: str = "Example Provider"
    # Where should the user go if they click on this?
    url: HttpUrl = HttpUrl(url="https://example.org")
    # What score should this result get when compared with other suggestions?
    score: float = BASE_SUGGEST_SCORE

    @abstractmethod
    def as_suggestion(self) -> BaseSuggestion:
        """Convert the result into a suggestion for publication"""
        ...
