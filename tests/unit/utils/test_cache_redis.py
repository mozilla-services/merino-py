# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the Redis cache adapter."""

import pytest
from unittest.mock import AsyncMock

from redis.asyncio import Redis, RedisError
from pytest_mock import MockerFixture

from merino.cache.redis import create_redis_clients, RedisAdapter
from merino.exceptions import CacheAdapterError


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


class TestSetNx:
    """Tests for RedisAdapter.set_nx."""

    @pytest.mark.asyncio
    async def test_returns_true_when_key_set(self) -> None:
        """Return True when the key was newly created."""
        mock_primary = AsyncMock()
        mock_primary.set.return_value = True
        adapter = RedisAdapter(mock_primary)

        result = await adapter.set_nx("lock:key", 30)

        assert result is True
        mock_primary.set.assert_called_once_with("lock:key", b"1", nx=True, ex=30)

    @pytest.mark.asyncio
    async def test_returns_false_when_key_exists(self) -> None:
        """Return False when the key already exists (Redis returns None)."""
        mock_primary = AsyncMock()
        mock_primary.set.return_value = None
        adapter = RedisAdapter(mock_primary)

        result = await adapter.set_nx("lock:key", 30)

        assert result is False

    @pytest.mark.asyncio
    async def test_raises_cache_adapter_error_on_redis_error(self) -> None:
        """Raise CacheAdapterError when Redis returns an error."""
        mock_primary = AsyncMock()
        mock_primary.set.side_effect = RedisError("connection lost")
        adapter = RedisAdapter(mock_primary)

        with pytest.raises(CacheAdapterError, match="SETNX"):
            await adapter.set_nx("lock:key", 30)


class TestDelete:
    """Tests for RedisAdapter.delete."""

    @pytest.mark.asyncio
    async def test_deletes_key(self) -> None:
        """Delete a key from Redis."""
        mock_primary = AsyncMock()
        adapter = RedisAdapter(mock_primary)

        await adapter.delete("lock:key")

        mock_primary.delete.assert_called_once_with("lock:key")

    @pytest.mark.asyncio
    async def test_raises_cache_adapter_error_on_redis_error(self) -> None:
        """Raise CacheAdapterError when Redis returns an error."""
        mock_primary = AsyncMock()
        mock_primary.delete.side_effect = RedisError("connection lost")
        adapter = RedisAdapter(mock_primary)

        with pytest.raises(CacheAdapterError, match="DELETE"):
            await adapter.delete("lock:key")
