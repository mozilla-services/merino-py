"""Abstract class for Providers"""
from abc import ABC, abstractmethod

from pydantic import BaseModel, HttpUrl

from merino.config import settings
from merino.middleware.geolocation import Location


class SuggestionRequest(BaseModel):
    """A request for suggestions."""

    query: str
    geolocation: Location


class BaseSuggestion(BaseModel):
    """Base model for suggestions. Each provider should extend this class for
    its specific suggestion model.
    """

    title: str
    url: HttpUrl
    provider: str
    is_sponsored: bool
    score: float
    icon: str | None = None


class BaseProvider(ABC):
    """Abstract class for suggestion providers."""

    _name: str
    _enabled_by_default: bool
    _query_timeout_sec: float = settings.runtime.query_timeout_sec

    @abstractmethod
    async def initialize(self) -> None:  # pragma: no cover
        """Abstract method for defining an initialize method for bootstrapping the Provider.
        This allows us to use Async API's within as well as initialize providers in parallel

        """
        ...

    async def shutdown(self) -> None:  # pragma: no cover
        """Shut down the Provider. The default implementaion is no-op."""
        return

    @abstractmethod
    async def query(
        self, srequest: SuggestionRequest
    ) -> list[BaseSuggestion]:  # pragma: no cover
        """Query against this provider.

        Args:
          - `srequest`: the suggestion request.
        """
        ...

    def _normalize_query(self, query: str) -> str:  # pragma: no cover
        """Normalize the query string when passed to the provider.
        Each provider can extend this class given its requirements. Can be used to
        strip whitespace, handle case sensitivity, etc. Default is to return query unchanged.

        Trailing spaces are not stripped in Firefox, so stripping trailing spaces
        is advised. Each provider will have its specific use cases, and others
        will not require any logic for query normalization.
        """
        return query

    @property
    def enabled_by_default(self) -> bool:
        """Boolean indicating whether or not provider is enabled."""
        return self._enabled_by_default

    def hidden(self) -> bool:
        """Boolean indicating whether or not this provider is hidden."""
        return False

    def availability(self) -> str:
        """Return the status of this provider."""
        if self.hidden():
            return "hidden"
        elif self.enabled_by_default:
            return "enabled_by_default"
        else:
            return "disabled_by_default"

    @property
    def name(self) -> str:
        """Return the name of the provider for use in logging and metrics"""
        return self._name

    @property
    def query_timeout_sec(self) -> float:
        """Return the query timeout for this provider."""
        return self._query_timeout_sec
