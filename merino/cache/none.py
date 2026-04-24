"""No-operation adapter that disables caching."""

from datetime import timedelta
from typing import Any


class NoCacheAdapter:  # pragma: no cover
    """A cache adapter that doesn't store or return anything."""

    async def get(self, key: str) -> bytes | None:  # noqa: D102
        return None

    async def set(  # noqa: D102
        self,
        key: str,
        value: bytes | str,
        ttl: timedelta | None = None,
    ) -> None:
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

    async def hexists(self, key: str, field: str) -> int:
        """Check if a hash field exists"""
        return 0

    async def hget(self, key: str, field: str) -> Any | None:
        """Return the field value for a hash key"""
        return None

    async def hmget(self, key: str, fields: list[str]) -> list[Any] | None:
        """Return values for multiple keys for a hash key"""
        return None

    async def hkeys(self, key: str) -> list[str] | None:
        """Return all field names for a hash key"""
        return None

    async def hvals(self, key: str) -> list[str] | None:
        """Return all field names for a hash key"""
        return None

    async def hgetall(self, key: str) -> dict[str, Any] | None:
        """Return all fields keys and values for a hash key"""
        return None

    async def hdel(self, key: str) -> int:
        """Remove a hash key record"""
        return 0

    async def hmset(self, key: str, values: dict[str, Any]) -> dict[str, Any] | None:
        """Return all fields for a hash key"""
        return None

    async def hsetnx(self, key: str, field: str, value: Any) -> int:
        """Set field for a hash key if not already present"""
        return 0

    # == Sorted Set functions
    async def zadd(
        self,
        key: str,
        mapping: dict[Any, int],
        nx: bool = False,
        xx: bool = False,
        gt: bool = False,
        lt: bool = False,
    ) -> int:
        """Set scored values (identified as a dict where the key is the name and the value is the score)

        an example of the mapping might be:
        {f"fifa:event:{eventId}": int(time.time())}

        flags:
            `nx`: if Not eXists
            `xx`: only if eXists
            `gt`: if provided value is Greater Than
            `lt`: if provided value is Less Than
        """
        return 0

    async def zrange(
        self,
        key: str,
        min: int,
        max: int,
        byScore: bool = True,
        limit: int | None = None,
        offset: int | None = None,
        rev: bool = False,
        withScores: bool = False,
    ) -> list[Any]:
        """Return values (with optional scores) that fall between the min and max inclusively"""
        return []

    async def zrem(
        self,
        key: str,
        *field: str,
    ) -> int:
        """Remove a field from a zrange key"""
        return 0

    async def zremrange(
        self,
        key: str,
        min: int,
        max: int,
    ) -> int:
        """Remove any values that fall between the min and max inclusively"""
        return 0

    async def setnx(self, key: str, value: Any) -> int:
        """Set a value if it is not present"""
        return 0
