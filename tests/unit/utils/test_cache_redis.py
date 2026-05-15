# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the cron.py module."""

import pytest
from pytest_mock import MockerFixture
from unittest.mock import MagicMock
from datetime import timedelta

from redis.asyncio import Redis, RedisError

from merino.exceptions import CacheAdapterError
from merino.cache.redis import create_redis_clients, RedisAdapter


@pytest.mark.asyncio
async def test_adapter_in_standalone_mode(mocker: MockerFixture) -> None:
    """Test `RedisAdapter` for the standalone mode."""
    spy = mocker.spy(Redis, "aclose")
    adapter: RedisAdapter = RedisAdapter(
        *create_redis_clients(
            primary="redis://localhost:6379",
            replica="redis://localhost:6379",
            max_connections=1,
            socket_connect_timeout=1,
            socket_timeout=1,
            db=0,
        )
    )

    assert adapter.primary is adapter.replica

    await adapter.close()

    spy.assert_called_once()


@pytest.mark.asyncio
async def test_delete_accepts_multiple_keys(mocker: MockerFixture) -> None:
    """RedisAdapter.delete delegates all variadic keys to Redis."""
    adapter = RedisAdapter(
        *create_redis_clients(
            primary="redis://localhost:6379",
            replica="redis://localhost:6379",
            max_connections=1,
            socket_connect_timeout=1,
            socket_timeout=1,
            db=0,
        )
    )
    mredis = MagicMock(spec=Redis)
    mredis.delete = mocker.AsyncMock(return_value=2)
    adapter.primary = mredis

    assert await adapter.delete("a", "b") == 2
    mredis.delete.assert_awaited_once_with("a", "b")


@pytest.mark.asyncio
async def test_adapter_functions(mocker: MockerFixture) -> None:
    """Test gauntlet of Redis functions (mostly for coverage)"""
    adapter: RedisAdapter = RedisAdapter(
        *create_redis_clients(
            primary="redis://localhost:6379",
            replica="redis://localhost:6379",
            max_connections=1,
            socket_connect_timeout=1,
            socket_timeout=1,
            db=0,
        )
    )
    mredis = MagicMock(spec=Redis)
    adapter.primary = mredis
    adapter.replica = mredis

    # purely for coverage:
    mredis.get.side_effect = RedisError
    mredis.mget.side_effect = RedisError
    mredis.set.side_effect = RedisError
    mredis.setnx.side_effect = RedisError
    mredis.delete.side_effect = RedisError
    mredis.hexists.side_effect = RedisError
    mredis.hget.side_effect = RedisError
    mredis.hset.side_effect = RedisError
    mredis.hmget.side_effect = RedisError
    mredis.hkeys.side_effect = RedisError
    mredis.hvals.side_effect = RedisError
    mredis.hgetall.side_effect = RedisError
    mredis.hdel.side_effect = RedisError
    mredis.hmset.side_effect = RedisError
    mredis.hsetnx.side_effect = RedisError
    mredis.zadd.side_effect = RedisError
    mredis.zrange.side_effect = RedisError
    mredis.zrem.side_effect = RedisError
    mredis.zremrangebyscore.side_effect = RedisError
    mredis.scan_iter.side_effect = RedisError

    expy = timedelta(seconds=30)
    with pytest.raises(CacheAdapterError):
        await adapter.get("key")
    with pytest.raises(CacheAdapterError):
        await adapter.mget([b"key"])
    with pytest.raises(CacheAdapterError):
        await adapter.set("key", b"value", expy)
    with pytest.raises(CacheAdapterError):
        await adapter.setnx("key", b"value", expy)
    with pytest.raises(CacheAdapterError):
        await adapter.delete("key")
    with pytest.raises(CacheAdapterError):
        await adapter.hexists("key", "field")
    with pytest.raises(CacheAdapterError):
        await adapter.hget("key", "value")
    with pytest.raises(CacheAdapterError):
        await adapter.hset("key", {"field": "value"})
    with pytest.raises(CacheAdapterError):
        await adapter.hmget("key", ["field"])
    with pytest.raises(CacheAdapterError):
        await adapter.hkeys("key")
    with pytest.raises(CacheAdapterError):
        await adapter.hvals("key")
    with pytest.raises(CacheAdapterError):
        await adapter.hgetall("key")
    with pytest.raises(CacheAdapterError):
        await adapter.hdel("key", "field")
    with pytest.raises(CacheAdapterError):
        await adapter.hmget("key", ["field"])
    with pytest.raises(CacheAdapterError):
        await adapter.hsetnx("key", "field", "value")
    with pytest.raises(CacheAdapterError):
        await adapter.zadd("key", {"field": 123}, nx=True)
    with pytest.raises(CacheAdapterError):
        await adapter.zrange("key", min=0, max=200)
    with pytest.raises(CacheAdapterError):
        await adapter.zrem("key", "field")
    with pytest.raises(CacheAdapterError):
        await adapter.zremrangebyscore("key", min=0, max=200)
    with pytest.raises(CacheAdapterError):
        await adapter.scan("key")
    with pytest.raises(CacheAdapterError):
        await adapter.set("key", b"value", ttl=expy, nx=False)
