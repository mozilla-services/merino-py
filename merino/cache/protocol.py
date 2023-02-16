"""Protocol for cache adapters."""

from datetime import timedelta
from typing import Optional, Protocol


class CacheAdapter(Protocol):
    """A protocol describing a cache backend."""

    async def get(self, key: str) -> Optional[bytes]:  # pragma: no cover
        """Get the value associated with the key. Returns `None` if the key isn't in the cache.

        Raises:
            - `CacheAdapterError` for cache backend errors.
        """
        ...

    async def set(
        self,
        key: str,
        value: bytes,
        ttl: Optional[timedelta] = None,
    ) -> None:  # pragma: no cover
        """Store a key-value pair in the cache, with an optional time-to-live.

        Raises:
            - `CacheAdapterError` for cache backend errors.
        """
        ...

    async def close(self) -> None:  # pragma: no cover
        """Close the adapter and release any underlying resources."""
        ...
