"""Merino specific exceptions."""


class BackendError(Exception):
    """Error specific to provider backend functions."""


class FilemanagerError(Exception):
    """Exception raised for errors processing data for backends."""

    pass


class InvalidProviderError(Exception):
    """Raised when an unknown provider encountered."""

    pass


class CacheAdapterError(Exception):
    """Exception raised when a cache adapter operation fails."""

    pass


class CacheEntryError(ValueError):
    """Exception raised for cache entries that can't be deserialized."""

    pass


class CacheMissError(Exception):
    """Exception raised if an entry doesn't exist in the cache."""

    pass


class CorpusCacheUnavailable(Exception):
    """Raised when the corpus cache cannot serve data.

    Triggers include: cold miss with lock held, circuit breaker open, or retry
    exhausted. The API layer translates this to HTTP 503.
    """

    pass
