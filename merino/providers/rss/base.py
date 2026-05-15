"""Abstract base class for RSS providers."""

from abc import ABC, abstractmethod


class BaseRssProvider(ABC):
    """Abstract base class for RSS providers."""

    _name: str
    _enabled_by_default: bool
    _query_timeout_sec: float

    def __init__(self, name: str, enabled_by_default: bool, query_timeout_sec: float) -> None:
        self._name = name
        self._enabled_by_default = enabled_by_default
        self._query_timeout_sec = query_timeout_sec

    @abstractmethod
    async def initialize(self) -> None:  # pragma: no cover
        """Initialize the provider."""
        ...

    async def shutdown(self) -> None:  # pragma: no cover
        """Shut down the provider. Default implementation is no-op."""
        return

    @property
    def name(self) -> str:
        """Return the name of this provider."""
        return self._name

    @property
    def enabled_by_default(self) -> bool:
        """Return whether this provider is enabled by default."""
        return self._enabled_by_default

    @property
    def query_timeout_sec(self) -> float:
        """Return the query timeout for this provider."""
        return self._query_timeout_sec
