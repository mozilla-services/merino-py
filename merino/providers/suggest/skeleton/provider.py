"""Provide a generic response"""

from abc import abstractmethod
import logging

import aiodogstatsd
from pydantic import HttpUrl

from merino.providers.suggest.base import (
    BaseProvider,
    BaseSuggestion,
    SuggestionRequest,
)

from merino.providers.suggest.skeleton.backends.emoji_picker.backend import (
    EmojiPickerBackend,
)

logger = logging.getLogger(__name__)


class SkeletonProvider(BaseProvider):
    """An example Provider.

    This needs to only define the abstracted methods specified by `BaseProvider`.
    This is the "workhorse" for the suggestion provider and is what is called directly
    from inside of merino's web CGI.

    """

    # The backend class we should use to process this request. This should be specified
    # by the child class override.
    backend: EmojiPickerBackend

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
        backend: EmojiPickerBackend,
        metrics_client: aiodogstatsd.Client,
        score: float,
        name: str,
        query_timeout_sec: float,
        enabled_by_default: bool = False,
    ):
        """Specify default values. NOTE: do not place any blocking or
        potentially fatal actions in this method. Those may cause Merino
        to fail to start up. Instead, use the `.initialize()` method
        """
        self.backend = backend
        self.metrics_client = metrics_client
        self.score = score
        self._name = name
        self._query_timeout_sec = query_timeout_sec
        self._enabled_by_default = enabled_by_default
        super().__init__()

    @abstractmethod
    async def initialize(self) -> None:
        """Create connections, components and other actions needed when starting up.
        This method is only called during general initialization, not on every call,
        so things that can take more than a few milliseconds should be done here.
        These should still be wrapped with `try`/`except`.
        """

    @abstractmethod
    def normalize_query(self, query: str) -> str:
        """Normalize means detecting keywords, stripping conflicting terms or stops, etc.
        **NOTE**: Python is "pass by value", meaning that any alteration done to the query will
        impact what is passed to other Providers.

        This function acts as a simple filter for the incoming query string, and the result is
        swapped into the SuggestionRequest for `.query()`. It may be useful to use this method
        to perform "intent word detection", and if no intent is discovered, this function could
        return an empty string, which would allow the `.query()` function to skip processing.

        Be sure to call ``super().normalize_query(query)`
        """
        return super().normalize_query(query)

    @abstractmethod
    def validate(self, srequest: SuggestionRequest) -> None:
        """Ensure that the incoming request is valid. This can involve checking incoming headers
        as well as other data outside of the content of the query string.

        Validation errors should raise an `HTTPException`.
        """
        return super().validate(srequest)

    @abstractmethod
    async def query(self, request: SuggestionRequest) -> list[BaseSuggestion]:
        """Handle the incoming query content from the URL bar.
        This function should fetch data from the backend, and format it into a list
        of suggestions that follow the agreed upon format.
        """
