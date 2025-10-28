"""Protocol for cache adapters."""

from datetime import timedelta
from typing import Any, Protocol


class CacheAdapter(Protocol):
    """A protocol describing a cache backend."""

    async def get(self, key: str) -> bytes | None:  # pragma: no cover
        """Get the value associated with the key. Returns `None` if the key isn't in the cache.

        Raises:
            - `CacheAdapterError` for cache backend errors.
        """
        ...

    async def set(
        self,
        key: str,
        value: bytes,
        ttl: timedelta | None = None,
    ) -> None:  # pragma: no cover
        """Store a key-value pair in the cache, with an optional time-to-live.

        Raises:
            - `CacheAdapterError` for cache backend errors.
        """
        ...

    async def close(self) -> None:  # pragma: no cover
        """Close the adapter and release any underlying resources."""
        ...

    def register_script(self, sid: str, script: str) -> None:  # pragma: no cover
        """Register a Lua script in Redis. Register multiple scripts using the same `sid`
        will overwrite the previous ones.

        Params:
            - `sid` {str}, a script identifier
            - `script` {str}, a Redis supported Lua script
        """
        ...

    async def run_script(
        self,
        sid: str,
        keys: list,
        args: list,
        readonly: bool = False,
    ) -> Any:  # pragma: no cover
        """Run a given script with keys and arguments.

        Params:
            - `sid` {str}, a script identifier
            - `keys` list[str], a list of keys used as the global `KEYS` in Redis scripting
            - `args` list[str], a list of arguments used as the global `ARGV` in Redis scripting
            - `readonly` bool, whether or not the script is readonly. Readonly scripts can be run on replica servers.
        Returns:
            A Redis value based on the return value of the specified script
        Raises:
            - `CacheAdapterError` if Redis returns an error.
        """
        ...

    async def sadd(self, key: str, *values: str) -> int:  # pragma: no cover
        """Add one or more values to a Redis set.

        Returns:
            Number of new elements added to the set.
        """
        ...

    async def sismember(self, key: str, value: str) -> bool:  # pragma: no cover
        """Check if a value is a member of a Redis set."""
        ...

    async def scard(self, key: str) -> int:  # pragma: no cover
        """Get the number of members in a Redis set."""
        ...

    async def ttl(self, key: str) -> int:  # pragma: no cover
        """Return the remaining time-to-live (TTL) in seconds for a given key.

        Args:
            key: The Redis key whose TTL should be retrieved.

        Returns:
            The TTL of the key in seconds. Returns -1 if the key exists but has no
            associated expiration, and -2 if the key does not exist.

        Raises:
            CacheAdapterError: If Redis encounters an error when fetching TTL.
        """
        ...

    async def zadd(self, key: str, mapping: dict[str, float]) -> int:  # pragma: no cover
        """Add one or more members with scores to a sorted set.

        Each member in the mapping is added to the sorted set with its score.
        If a member already exists, its score is updated. The score must be a
        numeric value (float or int).

        Args:
            key: The name of the sorted set.
            mapping: A dictionary where keys are members and values are scores.

        Returns:
            The number of new elements added to the sorted set (excluding updated ones).

        Raises:
            CacheAdapterError: If Redis encounters an error while adding members.
        """
        ...

    async def zrangebyscore(
        self, key: str, min: float, max: float
    ) -> list[bytes]:  # pragma: no cover
        """Retrieve all members in a sorted set whose scores fall within a given range.

        The returned members are ordered from lowest to highest score.

        Args:
            key: The name of the sorted set.
            min: The minimum score (inclusive).
            max: The maximum score (inclusive).

        Returns:
            A list of members (as bytes) whose scores fall within the specified range.

        Raises:
            CacheAdapterError: If Redis encounters an error during the query.
        """
        ...

    async def zremrangebyscore(self, key: str, min: float, max: float) -> int:  # pragma: no cover
        """Remove all members in a sorted set whose scores fall within a given range.

        Args:
            key: The name of the sorted set.
            min: The minimum score (inclusive).
            max: The maximum score (inclusive).

        Returns:
            The number of members removed from the sorted set.

        Raises:
            CacheAdapterError: If Redis encounters an error during removal.
        """
