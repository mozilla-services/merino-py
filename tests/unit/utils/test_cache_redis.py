# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the cron.py module."""

import pytest
from pytest_mock import MockerFixture
from unittest.mock import MagicMock
from time import time

from redis.asyncio import Redis, RedisError

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
    mredis.delete.side_effect = RedisError
    mredis.hexists.side_effect = RedisError
    mredis.hget.side_effect = RedisError
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
    mredis.scan.side_effect = RedisError
    mredis.setnx.side_effect = RedisError

    expy = time() + 60
    with pytest.raises(RedisError):
        await mredis.delete("key")
    with pytest.raises(RedisError):
        await mredis.hexists("key", "field")
    with pytest.raises(RedisError):
        await mredis.hget("key")
    with pytest.raises(RedisError):
        await mredis.hmget("key", "field")
    with pytest.raises(RedisError):
        await mredis.hkeys("key", ["field"])
    with pytest.raises(RedisError):
        await mredis.hvals("key")
    with pytest.raises(RedisError):
        await mredis.hgetall("key")
    with pytest.raises(RedisError):
        await mredis.hdel("key", "field")
    with pytest.raises(RedisError):
        await mredis.hmset("key", {"field": 123})
    with pytest.raises(RedisError):
        await mredis.hsetnx("key", "field", "value", expy)
    with pytest.raises(RedisError):
        await mredis.zadd("key", {"field", 123}, nx=True)
    with pytest.raises(RedisError):
        await mredis.zrange("key", min=0, max=200)
    with pytest.raises(RedisError):
        await mredis.zrem("key", "field")
    with pytest.raises(RedisError):
        await mredis.zremrangebyscore("key", "field", min=0, max=200)
    with pytest.raises(RedisError):
        await mredis.scan("key")
    with pytest.raises(RedisError):
        await mredis.setnx("key", "value")
