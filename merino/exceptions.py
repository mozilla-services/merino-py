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
    """Raised when corpus cache has no data and another pod holds the revalidation lock.

    Signals the API layer to return 503 with Retry-After instead of blocking.
    """

    pass
