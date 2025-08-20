"""Example Suggest "live" provider"""

"""
We're extending the Merino FastAPI main, so there's a lot of configuration done elsewhere
"""

import asyncio
import logging
import time

import aiodogstatsd
from fastapi import HTTPException
from pydantic import BaseModel, HttpUrl
from typing import Protocol

from merino.configs import settings
from merino.providers.manifest.backends.protocol import ManifestData
from merino.providers.suggest.base import (
    BaseProvider,
    BaseSuggestion,
)
from merino.providers.suggest.custom_details import CustomDetails
from merino.utils import cron


class SkeletonManifest(ManifestData):
    """Site metadata description"""


class SkeletonBackend(Protocol):
    """Root class for all Skeleton backends"""

    logger: logging.Logger
    manifest_data: SkeletonManifest | None = None

    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)


class SkeletonData(BaseModel):
    """Root result type for all Skeleton backends"""

    # Required fields for the Suggestion:
    # Who provided this result?
    provider = "Example Provider"
    # Where should the user go if they click on this?
    url = HttpUrl(url="https://example.org")
    # What score should this result get when compared with other suggestions?
    score = 0.5

    def as_suggestion(self) -> BaseSuggestion:
        """Convert the result into a suggestion for publication"""
        ...


class Provider(BaseProvider):
    """A Sample provider that returns an emoji based on a word or phrase"""

    backend: SkeletonBackend
