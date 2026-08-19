"""No-operation adapter that disables caching."""

from datetime import timedelta
from typing import Any


class NoCacheAdapter:  # pragma: no cover
    """A cache adapter that doesn't store or return anything."""

    async def get(self, key: str) -> bytes | None:  # noqa: D102
        return None

    async def mget(self, keys: list[bytes]) -> None | list[Any]:
        """Get data for multiple keys"""
        return None

    async def delete(self, *keys: str) -> int | None:  # noqa: D102
        return None

    async def setnx(
        self, key: str, value: bytes, ttl: timedelta | None = None, nx: bool = False
    ) -> bool | None:
        """Store a key-value pair in Redis, if there is not previous value, and optionally
        expiring after the time-to-live.
        """
        return None

    async def set(  # noqa: D102
        self,
        key: str,
        value: bytes | str,
        ttl: timedelta | None = None,
        nx: bool = False,
    ) -> None:
        """Store a key-value pair in Redis, overwriting the previous value if set, and optionally
        expiring after the time-to-live.

        Raises:
            - `CacheAdapterError` if Redis returns an error.
        """
        pass

    async def close(self) -> None:  # noqa: D102
        pass

    def register_script(self, sid: str, script: str) -> None:  # noqa: D102
        pass

    async def run_script(  # noqa: D102
        self, sid: str, keys: list, args: list, readonly: bool = False
    ) -> Any:
        pass

    async def sadd(self, key: str, *values: str) -> int:  # noqa: D102
        return 0

    async def sismember(self, key: str, value: str) -> bool:  # noqa: D102
        return False

    async def scard(self, key: str) -> int:  # noqa: D102
        return 0

    # == Hash Functions
    async def hexists(self, key: str, field: str) -> int:
        """Check if a hash field exists"""
        return 0

    async def hget(self, key: str, field: str) -> Any | None:
        """Return the field value for a hash key"""
        return None

    async def hmget(self, key: str, fields: list[str]) -> list[Any] | None:
        """Return values for multiple keys for a hash key"""
        return None

    async def hkeys(self, key: str) -> list[bytes] | None:
        """Return all field names for a hash key"""
        return None

    async def hvals(self, key: str) -> list[bytes] | None:
        """Return all field names for a hash key"""
        return None

    async def hgetall(self, key: str) -> dict[bytes, Any] | None:
        """Return all fields keys and values for a hash key"""
        return None

    async def hdel(self, key: str, field: str) -> int:
        """Remove a hash key record"""
        return 0

    # Technically, dict[str, Any] works fine, but mypy complains.
    async def hset(self, key: str, values: dict[str, Any]) -> int:
        """Return all fields for a hash key"""
        return 0

    async def hsetnx(self, key: str, field: str, value: Any) -> int:
        """Set field for a hash key if not already present"""
        return 0

    async def scan(self, pattern: str, limit: int = 100) -> list[Any]:
        """Scan keys for matching values. NOTE: This is VERY slow and should be avoided."""
        return []
