"""Provide a generic response"""

import logging

import aiodogstatsd
from fastapi import HTTPException
from pydantic import HttpUrl

from merino.providers.suggest.base import (
    BaseProvider,
    SuggestionRequest,
)
from merino.providers.suggest.skeleton import (
    SkeletonBackend,
)


logger = logging.getLogger(__name__)


class SkeletonProvider(BaseProvider):
    """An example Provider.

    This needs to only define abstract methods specified by `BaseProvider`

    """

    # The backend class we should use to process this request. This should be specified
    # by the child class override.
    backend: SkeletonBackend

    # The metric client for dealing with stats.
    metrics_client: aiodogstatsd.Client

    # The weight of this Suggest (compared to other suggestions)
    score: float

    # URL to the data source
    url: HttpUrl

    # Internal name of this provider.
    _name: str
    # semi-private flag used by BaseProvider to determine if this module is enabled.
    _enabled_by_default: bool
    # semi-private timeout per request
    _query_timeout_sec: float

    def __init__(
        self,
        backend: SkeletonBackend,
        metrics_client: aiodogstatsd.Client,
        score: float,
        name: str,
        query_timeout_sec: float,
        enabled_by_default: bool = False,
    ):
        self.backend = backend
        self.metrics_client = metrics_client
        self.score = score
        self._name = name
        self._query_timeout_sec = query_timeout_sec
        self._enabled_by_default = enabled_by_default

        super().__init__()

    # Note: Query will still need to be defined by any class that derives from this class.

    def validate(self, srequest: SuggestionRequest) -> None:
        """Ensure that the query string is present. This is more than the BaseProvider wants."""
        if not srequest.query:
            raise HTTPException(
                status_code=400,
                detail="Invalid query parameters: `q` is missing",
            )

    async def initialize(self) -> None:
        """Perform all the one-off initialization functions required for this Provider.

        This can include things like caching database connections, initializing manifest data, creating cron jobs, etc.

        """
        # No need to call super().initialize() since it's an abstract method.
        pass
