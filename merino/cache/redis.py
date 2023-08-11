"""Redis cache adapter."""

from datetime import timedelta
from typing import Any, Optional

from redis.asyncio import Redis, RedisError
from redis.commands.core import AsyncScript

from merino.exceptions import CacheAdapterError


class RedisAdapter:
    """A cache adapter that stores key-value pairs in Redis."""

    redis: Redis
    scripts: dict[str, AsyncScript] = {}

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
            await self.redis.set(
                key, value, ex=ttl.days * 86400 + ttl.seconds if ttl else None
            )
        except RedisError as exc:
            raise CacheAdapterError(
                f"Failed to set `{repr(key)}` with error: `{exc}`"
            ) from exc

    async def close(self) -> None:
        """Close the Redis connection."""
        await self.redis.close()

    def register_script(self, sid: str, script: str) -> None:
        """Register a Lua script in Redis. Regist multiple scripts using the same `sid`
        will overwrite the previous ones.

        Note that script registration is lazy, no network call will be made for this.

        Params:
            - `sid` {str}, a script identifier
            - `script` {str}, a Redis supported Lua script
        """
        self.scripts[sid] = self.redis.register_script(script)

    async def run_script(self, sid: str, keys: list[str], args: list[str]) -> Any:
        """Run a given script with keys and arguments.

        Params:
            - `sid` {str}, a script identifier
            - `keys` list[str], a list of keys used as the global `KEYS` in Redis scripting
            - `args` list[str], a list of arguments used as the global `ARGV` in Redis scripting
        Returns:
            A Redis value based on the return value of the specified script
        Raises:
            - `CacheAdapterError` if Redis returns an error
            - `KeyError` if `sid` does not have a script associated
        """
        try:
            res = await self.scripts[sid](keys, args)
        except RedisError as exc:
            raise CacheAdapterError(
                f"Failed to run script {id} with error: `{exc}`"
            ) from exc

        return res
