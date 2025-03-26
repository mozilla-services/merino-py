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
