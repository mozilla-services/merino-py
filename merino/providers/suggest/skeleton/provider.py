"""Provide a generic response"""

import logging

import aiodogstatsd
from pydantic import HttpUrl

from merino.providers.suggest.base import (
    BaseProvider,
)
from merino.providers.suggest.skeleton import (
    SkeletonBackend,
)


logger = logging.getLogger(__name__)


class SkeletonProvider(BaseProvider):
    """An example Provider.

    This needs to only define the abstracted methods specified by `BaseProvider`

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

    # Note:
    # The following will need to be implemented by the Provider:
    #
    # def validate(self, srequest: SuggestionRequest) -> None:
    #   """Ensure the content of the `srequest` is valid"""
    #
    # async def initialize(self) -> None:
    #   """Perform all one-off initialization functions required
    #
    #   This can include things like establishing or pooling database connections,
    #   creating cron tasks, etc.
    #   """
    #
    # async def query(self, request: SuggestionRequest) -> list[BaseSuggestion]:
    #   """Process the incoming request and return a list of the suggestions."
