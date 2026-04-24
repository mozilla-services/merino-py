"""Redis cache adapter."""

import inspect
import types
from datetime import timedelta
from typing import Any, cast

from redis.asyncio import Redis, RedisError
from redis.commands.core import AsyncScript
from redis.typing import EncodableT

from merino.exceptions import CacheAdapterError


def create_redis_clients(
    primary: str,
    replica: str,
    max_connections: int,
    socket_connect_timeout: int,
    socket_timeout: int,
    db: int = 0,
) -> tuple[Redis, Redis]:
    """Create redis clients for the primary and replica severs.
    When `replica` is the same as `primary`, the returned clients are the same.

    Args:
        - `primary`: the URL to the Redis primary endpoint.
        - `replica`: the URL to the Redis replica endpoint.
        - `max_connections`: the maximum connections allowed in the connection pool.
        - `socket_connect_timeout`: the timeout in seconds to connect to the Redis server.
        - `socket_timeout`: the timeout in seconds to interact with the Redis server.
        - `db`: the ID (`SELECT db`) of the DB to which the clients connect.
    Returns:
        - A tuple of two clients, the first for the primary server and the second for the replica endpoint.
          When `primary` is the same as `replica`, the two share the same underlying client.
    """
    client_primary: Redis = Redis.from_url(
        primary,
        db=db,
        max_connections=max_connections,
        socket_connect_timeout=socket_connect_timeout,
        socket_timeout=socket_timeout,
    )
    client_replica: Redis
    if primary == replica:
        client_replica = client_primary
    else:
        client_replica = Redis.from_url(
            replica,
            db=db,
            max_connections=max_connections,
            socket_connect_timeout=socket_connect_timeout,
            socket_timeout=socket_timeout,
        )

    return client_primary, client_replica


class RedisAdapter:
    """A cache adapter for Redis.
    Merino's Redis server employes replication for high availability. Hence
    each adapter maintains two clients connected to the primary endpoint and
    the replica endpoint, respectively. To ease the development and testing,
    the primary and replica clients can be set to the same underlying client,
    all the commands should work as expected in both primary-replica and
    standalone modes.

    Note that only readonly commands can be executed on the replica nodes.
    """

    primary: Redis
    replica: Redis
    scripts: dict[str, AsyncScript] = {}

    def __init__(self, primary: Redis, replica: Redis | None = None):
        self.primary = primary
        self.replica = replica or primary

    async def get(self, key: str) -> bytes | None:
        """Get the value associated with the key from Redis. Returns `None` if the key isn't in
        Redis.

        Raises:
            - `CacheAdapterError` if Redis returns an error.
        """
        try:
            return await self.replica.get(key)
        except RedisError as exc:
            raise CacheAdapterError(f"Failed to get `{repr(key)}` with error: `{exc}`") from exc

    async def set(
        self,
        key: str,
        value: bytes,
        ttl: timedelta | None = None,
    ) -> None:
        """Store a key-value pair in Redis, overwriting the previous value if set, and optionally
        expiring after the time-to-live.

        Raises:
            - `CacheAdapterError` if Redis returns an error.
        """
        try:
            await self.primary.set(key, value, ex=ttl.days * 86400 + ttl.seconds if ttl else None)
        except RedisError as exc:
            raise CacheAdapterError(f"Failed to set `{repr(key)}` with error: `{exc}`") from exc

    async def sadd(self, key: str, *values: str) -> int:
        """Add one or more values to a Redis set.

        Returns:
            Number of new elements added to the set.
        """
        try:
            return await self.primary.sadd(key, *values)
        except RedisError as exc:
            raise CacheAdapterError(f"Failed to SADD {key} with error: {exc}") from exc

    async def sismember(self, key: str, value: str) -> bool:
        """Check if a value is a member of a Redis set."""
        try:
            return bool(await self.replica.sismember(key, value))
        except RedisError as exc:
            raise CacheAdapterError(f"Failed to SISMEMBER {key} with error: {exc}") from exc

    async def scard(self, key: str) -> int:
        """Get the number of members in a Redis set."""
        try:
            return await self.replica.scard(key)
        except RedisError as exc:
            raise CacheAdapterError(f"Failed to SCARD {key} with error: {exc}") from exc

    # == Hash Functions
    async def hexists(self, key: str, field: str) -> int:
        """Check if a hash field exists"""
        try:
            return await self.replica.hexists(key, field)
        except RedisError as exc:
            raise CacheAdapterError(
                f"Failed to {cast(types.FrameType, inspect.currentframe()).f_code.co_name.upper()} {key} with error: {exc}"
            ) from exc

    async def hget(self, key: str, field: str) -> EncodableT | None:
        """Return the field value for a hash key"""
        try:
            return await self.replica.hget(key, field)
        except RedisError as exc:
            raise CacheAdapterError(
                f"Failed to {cast(types.FrameType, inspect.currentframe()).f_code.co_name.upper()} {key} with error: {exc}"
            ) from exc

    async def hmget(self, key: str, fields: list[str]) -> list[Any] | None:
        """Return values for multiple keys for a hash key"""
        try:
            return await self.replica.hmget(key, fields)
        except RedisError as exc:
            raise CacheAdapterError(
                f"Failed to {cast(types.FrameType, inspect.currentframe()).f_code.co_name.upper()} {key} with error: {exc}"
            ) from exc

    async def hkeys(self, key: str) -> list[str] | None:
        """Return all field names for a hash key"""
        try:
            return await self.replica.hkeys(key)
        except RedisError as exc:
            raise CacheAdapterError(
                f"Failed to {cast(types.FrameType, inspect.currentframe()).f_code.co_name.upper()} {key} with error: {exc}"
            ) from exc

    async def hvals(self, key: str) -> list[str] | None:
        """Return all field names for a hash key"""
        try:
            return await self.replica.hvals(key)
        except RedisError as exc:
            raise CacheAdapterError(
                f"Failed to {cast(types.FrameType, inspect.currentframe()).f_code.co_name.upper()} {key} with error: {exc}"
            ) from exc

    async def hgetall(self, key: str) -> dict[str, Any] | None:
        """Return all fields keys and values for a hash key"""
        try:
            return await self.replica.hgetall(key)
        except RedisError as exc:
            raise CacheAdapterError(
                f"Failed to {cast(types.FrameType, inspect.currentframe()).f_code.co_name.upper()} {key} with error: {exc}"
            ) from exc

    async def hdel(self, key: str) -> int:
        """Remove a hash key record"""
        try:
            return await self.primary.hdel(key)
        except RedisError as exc:
            raise CacheAdapterError(
                f"Failed to {cast(types.FrameType, inspect.currentframe()).f_code.co_name.upper()} {key} with error: {exc}"
            ) from exc

    async def hmset(self, key: str, values: dict[str, Any]) -> dict[str, Any] | None:
        """Return all fields for a hash key"""
        try:
            return await self.primary.hgetall(key)
        except RedisError as exc:
            raise CacheAdapterError(
                f"Failed to {cast(types.FrameType, inspect.currentframe()).f_code.co_name.upper()} {key} with error: {exc}"
            ) from exc

    async def hsetnx(self, key: str, field: str, value: Any) -> int:
        """Set field for a hash key if not already present"""
        try:
            return await self.primary.hsetnx(key, field, value)
        except RedisError as exc:
            raise CacheAdapterError(
                f"Failed to {cast(types.FrameType, inspect.currentframe()).f_code.co_name.upper()} {key} with error: {exc}"
            ) from exc

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
        try:
            return await self.primary.zadd(key, mapping, nx=nx, xx=xx, gt=gt, lt=lt)
        except RedisError as exc:
            raise CacheAdapterError(
                f"Failed to {cast(types.FrameType, inspect.currentframe()).f_code.co_name.upper()} {key} with error: {exc}"
            ) from exc

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
        try:
            return await self.replica.zrange(
                key,
                start=min,
                end=max,
                desc=rev,
                withscores=withScores,
                byscore=byScore,
                offset=offset,
                num=limit,
            )
        except RedisError as exc:
            raise CacheAdapterError(
                f"Failed to {cast(types.FrameType, inspect.currentframe()).f_code.co_name.upper()} {key} with error: {exc}"
            ) from exc

    async def zrem(
        self,
        key: str,
        *field: str,
    ) -> int:
        """Remove a field from a zrange key"""
        try:
            return await self.replica.zrem(
                key,
                *field,
            )
        except RedisError as exc:
            raise CacheAdapterError(
                f"Failed to {cast(types.FrameType, inspect.currentframe()).f_code.co_name.upper()} {key} with error: {exc}"
            ) from exc

    async def zremrange(
        self,
        key: str,
        min: int,
        max: int,
    ) -> int:
        """Remove any values that fall between the min and max inclusively"""
        try:
            return await self.replica.zremrangebyscore(
                name=key,
                min=min,
                max=max,
            )
        except RedisError as exc:
            raise CacheAdapterError(
                f"Failed to {cast(types.FrameType, inspect.currentframe()).f_code.co_name.upper()} {key} with error: {exc}"
            ) from exc

    # ==
    async def setnx(self, key: str, value: EncodableT) -> int:
        """Set a value if it is not present"""
        try:
            return await self.primary.setnx(key, value)
        except RedisError as exc:
            raise CacheAdapterError(
                f"Failed to {cast(types.FrameType, inspect.currentframe()).f_code.co_name.upper()} {key} with error: {exc}"
            ) from exc

    async def close(self) -> None:
        """Close the Redis connection."""
        if self.primary is self.replica:
            # "type: ignore" was added to suppress a false alarm.
            await self.primary.aclose()  # type: ignore
        else:
            await self.primary.aclose()  # type: ignore
            await self.replica.aclose()  # type: ignore

    def register_script(self, sid: str, script: str) -> None:
        """Register a Lua script in Redis. Regist multiple scripts using the same `sid`
        will overwrite the previous ones.

        Note that script registration is lazy, no network call will be made for this.

        Params:
            - `sid` {str}, a script identifier
            - `script` {str}, a Redis supported Lua script
        """
        self.scripts[sid] = self.primary.register_script(script)

    async def run_script(
        self, sid: str, keys: list[str], args: list[str], readonly: bool = False
    ) -> Any:
        """Run a given script with keys and arguments.

        Params:
            - `sid` {str}, a script identifier
            - `keys` list[str], a list of keys used as the global `KEYS` in Redis scripting
            - `args` list[str], a list of arguments used as the global `ARGV` in Redis scripting
            - `readonly` bool, whether or not the script is readonly. Readonly scripts will be run on replica servers.
        Returns:
            A Redis value based on the return value of the specified script
        Raises:
            - `CacheAdapterError` if Redis returns an error
            - `KeyError` if `sid` does not have a script associated
        """
        try:
            # Run the script in the replica nodes if it's readonly.
            res = await self.scripts[sid](keys, args, self.replica if readonly else self.primary)
        except RedisError as exc:
            raise CacheAdapterError(f"Failed to run script {id} with error: `{exc}`") from exc

        return res
