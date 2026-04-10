# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the Redis cache adapter."""

import pytest
from unittest.mock import AsyncMock, MagicMock

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


class TestGet:
    """Tests for RedisAdapter.get."""

    @pytest.mark.asyncio
    async def test_returns_value(self) -> None:
        """Return the value for an existing key."""
        mock_replica = AsyncMock()
        mock_replica.get.return_value = b"data"
        adapter = RedisAdapter(AsyncMock(), mock_replica)

        assert await adapter.get("key") == b"data"
        mock_replica.get.assert_called_once_with("key")

    @pytest.mark.asyncio
    async def test_returns_none_for_missing_key(self) -> None:
        """Return None when the key does not exist."""
        mock_replica = AsyncMock()
        mock_replica.get.return_value = None
        adapter = RedisAdapter(AsyncMock(), mock_replica)

        assert await adapter.get("key") is None

    @pytest.mark.asyncio
    async def test_raises_cache_adapter_error_on_redis_error(self) -> None:
        """Raise CacheAdapterError when Redis returns an error."""
        mock_replica = AsyncMock()
        mock_replica.get.side_effect = RedisError("connection lost")
        adapter = RedisAdapter(AsyncMock(), mock_replica)

        with pytest.raises(CacheAdapterError, match="get"):
            await adapter.get("key")


class TestSet:
    """Tests for RedisAdapter.set."""

    @pytest.mark.asyncio
    async def test_sets_value_with_ttl(self) -> None:
        """Store a value with a TTL."""
        from datetime import timedelta

        mock_primary = AsyncMock()
        adapter = RedisAdapter(mock_primary)

        await adapter.set("key", b"val", ttl=timedelta(seconds=60))

        mock_primary.set.assert_called_once_with("key", b"val", ex=60)

    @pytest.mark.asyncio
    async def test_sets_value_without_ttl(self) -> None:
        """Store a value without a TTL."""
        mock_primary = AsyncMock()
        adapter = RedisAdapter(mock_primary)

        await adapter.set("key", b"val")

        mock_primary.set.assert_called_once_with("key", b"val", ex=None)

    @pytest.mark.asyncio
    async def test_raises_cache_adapter_error_on_redis_error(self) -> None:
        """Raise CacheAdapterError when Redis returns an error."""
        mock_primary = AsyncMock()
        mock_primary.set.side_effect = RedisError("connection lost")
        adapter = RedisAdapter(mock_primary)

        with pytest.raises(CacheAdapterError, match="set"):
            await adapter.set("key", b"val")


class TestSadd:
    """Tests for RedisAdapter.sadd."""

    @pytest.mark.asyncio
    async def test_returns_count_of_new_members(self) -> None:
        """Return the number of new elements added."""
        mock_primary = AsyncMock()
        mock_primary.sadd.return_value = 2
        adapter = RedisAdapter(mock_primary)

        result = await adapter.sadd("myset", "a", "b")

        assert result == 2
        mock_primary.sadd.assert_called_once_with("myset", "a", "b")

    @pytest.mark.asyncio
    async def test_raises_cache_adapter_error_on_redis_error(self) -> None:
        """Raise CacheAdapterError when Redis returns an error."""
        mock_primary = AsyncMock()
        mock_primary.sadd.side_effect = RedisError("connection lost")
        adapter = RedisAdapter(mock_primary)

        with pytest.raises(CacheAdapterError, match="SADD"):
            await adapter.sadd("myset", "a")


class TestSismember:
    """Tests for RedisAdapter.sismember."""

    @pytest.mark.asyncio
    async def test_returns_true_for_member(self) -> None:
        """Return True when the value is in the set."""
        mock_replica = AsyncMock()
        mock_replica.sismember.return_value = 1
        adapter = RedisAdapter(AsyncMock(), mock_replica)

        assert await adapter.sismember("myset", "a") is True

    @pytest.mark.asyncio
    async def test_returns_false_for_non_member(self) -> None:
        """Return False when the value is not in the set."""
        mock_replica = AsyncMock()
        mock_replica.sismember.return_value = 0
        adapter = RedisAdapter(AsyncMock(), mock_replica)

        assert await adapter.sismember("myset", "z") is False

    @pytest.mark.asyncio
    async def test_raises_cache_adapter_error_on_redis_error(self) -> None:
        """Raise CacheAdapterError when Redis returns an error."""
        mock_replica = AsyncMock()
        mock_replica.sismember.side_effect = RedisError("connection lost")
        adapter = RedisAdapter(AsyncMock(), mock_replica)

        with pytest.raises(CacheAdapterError, match="SISMEMBER"):
            await adapter.sismember("myset", "a")


class TestScard:
    """Tests for RedisAdapter.scard."""

    @pytest.mark.asyncio
    async def test_returns_set_size(self) -> None:
        """Return the cardinality of the set."""
        mock_replica = AsyncMock()
        mock_replica.scard.return_value = 5
        adapter = RedisAdapter(AsyncMock(), mock_replica)

        assert await adapter.scard("myset") == 5

    @pytest.mark.asyncio
    async def test_raises_cache_adapter_error_on_redis_error(self) -> None:
        """Raise CacheAdapterError when Redis returns an error."""
        mock_replica = AsyncMock()
        mock_replica.scard.side_effect = RedisError("connection lost")
        adapter = RedisAdapter(AsyncMock(), mock_replica)

        with pytest.raises(CacheAdapterError, match="SCARD"):
            await adapter.scard("myset")


class TestClose:
    """Tests for RedisAdapter.close when primary and replica differ."""

    @pytest.mark.asyncio
    async def test_closes_both_clients(self) -> None:
        """Close both primary and replica when they are different objects."""
        mock_primary = AsyncMock()
        mock_replica = AsyncMock()
        # Ensure they are distinct objects
        assert mock_primary is not mock_replica
        adapter = RedisAdapter(mock_primary, mock_replica)

        await adapter.close()

        mock_primary.aclose.assert_called_once()
        mock_replica.aclose.assert_called_once()


class TestRegisterAndRunScript:
    """Tests for RedisAdapter.register_script and run_script."""

    @pytest.mark.asyncio
    async def test_run_script_on_primary(self) -> None:
        """Run a registered script on the primary client."""
        mock_primary = AsyncMock()

        async def script_fn(*args: object) -> str:
            return "ok"

        mock_script = MagicMock(side_effect=script_fn)
        # register_script is synchronous on Redis
        mock_primary.register_script = MagicMock(return_value=mock_script)
        adapter = RedisAdapter(mock_primary)

        adapter.register_script("myscript", "return 1")
        result = await adapter.run_script("myscript", keys=["k"], args=["a"])

        assert result == "ok"
        mock_script.assert_called_once_with(["k"], ["a"], mock_primary)

    @pytest.mark.asyncio
    async def test_run_script_readonly_uses_replica(self) -> None:
        """Run a readonly script on the replica client."""
        mock_primary = AsyncMock()
        mock_replica = AsyncMock()

        async def script_fn(*args: object) -> str:
            return "ok"

        mock_script = MagicMock(side_effect=script_fn)
        mock_primary.register_script = MagicMock(return_value=mock_script)
        adapter = RedisAdapter(mock_primary, mock_replica)

        adapter.register_script("myscript", "return 1")
        result = await adapter.run_script("myscript", keys=["k"], args=["a"], readonly=True)

        assert result == "ok"
        mock_script.assert_called_once_with(["k"], ["a"], mock_replica)

    @pytest.mark.asyncio
    async def test_run_script_raises_on_redis_error(self) -> None:
        """Raise CacheAdapterError when the script fails."""
        mock_primary = AsyncMock()

        async def raise_redis_error(*args: object) -> None:
            raise RedisError("script error")

        mock_script = MagicMock(side_effect=raise_redis_error)
        mock_primary.register_script = MagicMock(return_value=mock_script)
        adapter = RedisAdapter(mock_primary)

        adapter.register_script("myscript", "return 1")
        with pytest.raises(CacheAdapterError, match="script"):
            await adapter.run_script("myscript", keys=["k"], args=["a"])


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
        mock_primary.set.assert_called_once_with("lock:key", b"1", nx=True, ex=30)

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
