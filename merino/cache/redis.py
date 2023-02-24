"""Redis cache adapter."""

from datetime import timedelta
from typing import Optional

from redis.asyncio import Redis, RedisError

from merino.exceptions import CacheAdapterError


class RedisAdapter:
    """A cache adapter that stores key-value pairs in Redis."""

    redis: Redis

    def __init__(self, redis: Redis):
        self.redis = redis

    async def get(self, key: str) -> Optional[bytes]:
        """Get the value associated with the key from Redis. Returns `None` if the key isn't in
        Redis.

        Raises:
            - `CacheAdapterError` if Redis returns an error.
        """
        try:
            return await self.redis.get(key)
        except RedisError as exc:
            raise CacheAdapterError(
                f"Failed to get `{repr(key)}` with error: `{exc}`"
            ) from exc

    async def set(
        self,
        key: str,
        value: bytes,
        ttl: Optional[timedelta] = None,
    ) -> None:
        """Store a key-value pair in Redis, overwriting the previous value if set, and optionally
        expiring after the time-to-live.

        Raises:
            - `CacheAdapterError` if Redis returns an error.
        """
        try:
            await self.redis.set(key, value, ex=ttl.seconds if ttl else None)
        except RedisError as exc:
            raise CacheAdapterError(
                f"Failed to set `{repr(key)}` with error: `{exc}`"
            ) from exc

    async def close(self) -> None:
        """Close the Redis connection."""
        await self.redis.close()
