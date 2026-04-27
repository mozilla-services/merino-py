"""Unit tests for the Redis L2 corpus cache layer."""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import aiodogstatsd
import orjson
import pytest

from merino.curated_recommendations.corpus_backends.protocol import (
    CorpusSection,
    CreateSource,
    SurfaceId,
)
from merino.curated_recommendations.corpus_backends.redis_cache import (
    BackendType,
    CorpusCacheConfig,
    CorpusCacheUnavailable,
    RedisCachedScheduledSurface,
    RedisCachedSections,
    _RedisCorpusCache,
    _build_data_key,
    _build_lock_key,
    _deserialize_envelope,
    _serialize_envelope,
)
from merino.exceptions import CacheAdapterError
from tests.unit.curated_recommendations.test_sections import generate_corpus_item

SURFACE_ID = SurfaceId.NEW_TAB_EN_US

CONFIG = CorpusCacheConfig(
    soft_ttl_sec=60,
    hard_ttl_sec=600,
    lock_ttl_sec=30,
    key_prefix="curated:v1",
)


def _make_corpus_section() -> CorpusSection:
    """Create a CorpusSection with sensible defaults for testing."""
    return CorpusSection(
        sectionItems=[generate_corpus_item()],
        title="Test Section",
        externalId="test-section",
        createSource=CreateSource.ML,
    )


def _make_fresh_envelope(items_data: list[dict], soft_ttl_sec: int = 60) -> bytes:
    """Create a serialized cache envelope that is still fresh."""
    return _serialize_envelope(items_data, soft_ttl_sec)


def _make_stale_envelope(items_data: list[dict]) -> bytes:
    """Create a serialized cache envelope that has already expired."""
    envelope = {
        "expires_at": time.time() - 10,
        "data": items_data,
    }
    return orjson.dumps(envelope)


class TestKeyBuilders:
    """Tests for Redis key construction functions."""

    @pytest.mark.parametrize(
        ("backend_type", "expected"),
        [
            ("scheduled", "curated:v1:scheduled:NEW_TAB_EN_US"),
            ("sections", "curated:v1:sections:NEW_TAB_EN_US"),
        ],
        ids=["scheduled", "sections"],
    )
    def test_build_data_key(self, backend_type: BackendType, expected: str) -> None:
        """Build a data key for the given backend type."""
        assert _build_data_key(CONFIG, backend_type, SurfaceId.NEW_TAB_EN_US) == expected

    def test_build_lock_key(self) -> None:
        """Build a lock key with 'lock' segment inserted."""
        key = _build_lock_key(CONFIG, "scheduled", SurfaceId.NEW_TAB_EN_US)
        assert key == "curated:v1:lock:scheduled:NEW_TAB_EN_US"


class TestEnvelope:
    """Tests for envelope serialization and deserialization."""

    def test_roundtrip(self) -> None:
        """Serialize and deserialize an envelope."""
        data = [{"corpusItemId": "abc", "title": "Hello"}]
        raw = _serialize_envelope(data, soft_ttl_sec=60)
        expires_at, deserialized = _deserialize_envelope(raw)
        assert deserialized == data
        assert expires_at > time.time()

    def test_deserialize_invalid_json(self) -> None:
        """Raise on invalid JSON bytes."""
        with pytest.raises(orjson.JSONDecodeError):
            _deserialize_envelope(b"not json")


class TestRedisCorpusCache:
    """Tests for the shared _RedisCorpusCache logic."""

    def setup_method(self) -> None:
        """Set up mock cache adapter and helper functions."""
        self.mock_cache = AsyncMock()
        self.metrics_client = MagicMock(spec=aiodogstatsd.Client)
        self.redis_cache = _RedisCorpusCache(self.mock_cache, CONFIG, self.metrics_client)
        self.fetch_fn = AsyncMock(return_value=["item1", "item2"])
        self.serialize_fn = lambda items: [{"v": i} for i in items]
        self.deserialize_fn = lambda data: [d["v"] for d in data]

    @pytest.mark.asyncio
    async def test_fresh_hit_returns_cached_data(self) -> None:
        """Return deserialized data on a fresh Redis hit without calling fetch_fn."""
        items_data = [{"v": "item1"}, {"v": "item2"}]
        self.mock_cache.get.return_value = _make_fresh_envelope(items_data)

        result = await self.redis_cache.get_or_fetch(
            "scheduled",
            SURFACE_ID,
            fetch_fn=self.fetch_fn,
            serialize_fn=self.serialize_fn,
            deserialize_fn=self.deserialize_fn,
        )

        assert result == ["item1", "item2"]
        self.fetch_fn.assert_not_called()
        self.mock_cache.set_nx.assert_not_called()

    @pytest.mark.asyncio
    async def test_stale_hit_lock_winner_revalidates(self) -> None:
        """Revalidate when stale and lock is acquired."""
        items_data = [{"v": "old"}]
        self.mock_cache.get.return_value = _make_stale_envelope(items_data)
        self.mock_cache.set_nx.return_value = True

        result = await self.redis_cache.get_or_fetch(
            "scheduled",
            SURFACE_ID,
            fetch_fn=self.fetch_fn,
            serialize_fn=self.serialize_fn,
            deserialize_fn=self.deserialize_fn,
        )

        assert result == ["item1", "item2"]
        self.fetch_fn.assert_called_once()
        self.mock_cache.set.assert_called_once()
        self.mock_cache.delete.assert_called_once_with("curated:v1:lock:scheduled:NEW_TAB_EN_US")

    @pytest.mark.asyncio
    async def test_stale_hit_lock_loser_returns_stale(self) -> None:
        """Return stale data when another pod holds the lock."""
        items_data = [{"v": "stale"}]
        self.mock_cache.get.return_value = _make_stale_envelope(items_data)
        self.mock_cache.set_nx.return_value = False

        result = await self.redis_cache.get_or_fetch(
            "scheduled",
            SURFACE_ID,
            fetch_fn=self.fetch_fn,
            serialize_fn=self.serialize_fn,
            deserialize_fn=self.deserialize_fn,
        )

        assert result == ["stale"]
        self.fetch_fn.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_lock_winner_fetches(self) -> None:
        """Fetch from backend on cache miss when lock is acquired."""
        self.mock_cache.get.return_value = None
        self.mock_cache.set_nx.return_value = True

        result = await self.redis_cache.get_or_fetch(
            "scheduled",
            SURFACE_ID,
            fetch_fn=self.fetch_fn,
            serialize_fn=self.serialize_fn,
            deserialize_fn=self.deserialize_fn,
        )

        assert result == ["item1", "item2"]
        self.fetch_fn.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_miss_lock_loser_retries_and_succeeds(self) -> None:
        """Wait and retry Redis when cache misses and lock is held by another pod."""
        items_data = [{"v": "item1"}, {"v": "item2"}]
        # First get returns None (miss), second get returns data (written by lock winner)
        self.mock_cache.get.side_effect = [None, _make_fresh_envelope(items_data)]
        self.mock_cache.set_nx.return_value = False

        result = await self.redis_cache.get_or_fetch(
            "scheduled",
            SURFACE_ID,
            fetch_fn=self.fetch_fn,
            serialize_fn=self.serialize_fn,
            deserialize_fn=self.deserialize_fn,
        )

        assert result == ["item1", "item2"]
        self.fetch_fn.assert_not_called()
        assert self.mock_cache.get.call_count == 2

    @pytest.mark.asyncio
    async def test_cache_miss_lock_loser_retries_then_raises_unavailable(self) -> None:
        """Raise CorpusCacheUnavailable when retry still finds no data after waiting."""
        self.mock_cache.get.return_value = None
        self.mock_cache.set_nx.return_value = False

        with pytest.raises(CorpusCacheUnavailable):
            await self.redis_cache.get_or_fetch(
                "scheduled",
                SURFACE_ID,
                fetch_fn=self.fetch_fn,
                serialize_fn=self.serialize_fn,
                deserialize_fn=self.deserialize_fn,
            )

        self.fetch_fn.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_lock_loser_retry_deserialize_error_raises_unavailable(
        self,
    ) -> None:
        """Raise CorpusCacheUnavailable when retry data can't be deserialized."""
        items_data = [{"v": "item1"}]
        self.mock_cache.get.side_effect = [None, _make_fresh_envelope(items_data)]
        self.mock_cache.set_nx.return_value = False

        def bad_deserialize(data: list[dict]) -> list:
            raise ValueError("schema changed")

        with pytest.raises(CorpusCacheUnavailable):
            await self.redis_cache.get_or_fetch(
                "scheduled",
                SURFACE_ID,
                fetch_fn=self.fetch_fn,
                serialize_fn=self.serialize_fn,
                deserialize_fn=bad_deserialize,
            )

        self.fetch_fn.assert_not_called()

    @pytest.mark.asyncio
    async def test_redis_read_error_falls_through(self) -> None:
        """Fall through to backend when Redis read fails."""
        self.mock_cache.get.side_effect = CacheAdapterError("connection refused")
        self.mock_cache.set_nx.return_value = True

        result = await self.redis_cache.get_or_fetch(
            "scheduled",
            SURFACE_ID,
            fetch_fn=self.fetch_fn,
            serialize_fn=self.serialize_fn,
            deserialize_fn=self.deserialize_fn,
        )

        assert result == ["item1", "item2"]
        self.fetch_fn.assert_called_once()

    @pytest.mark.asyncio
    async def test_redis_write_error_does_not_raise(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Continue normally when Redis write fails after fetching."""
        self.mock_cache.get.return_value = None
        self.mock_cache.set_nx.return_value = True
        self.mock_cache.set.side_effect = CacheAdapterError("write failed")

        result = await self.redis_cache.get_or_fetch(
            "scheduled",
            SURFACE_ID,
            fetch_fn=self.fetch_fn,
            serialize_fn=self.serialize_fn,
            deserialize_fn=self.deserialize_fn,
        )

        assert result == ["item1", "item2"]
        # Cache write was attempted (and failed), but lock should still be released
        self.mock_cache.set.assert_called_once()
        self.mock_cache.delete.assert_called_once_with("curated:v1:lock:scheduled:NEW_TAB_EN_US")
        assert any("write error" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_deserialization_error_falls_through(self) -> None:
        """Treat corrupted Redis data as a cache miss."""
        self.mock_cache.get.return_value = b"not valid json"
        self.mock_cache.set_nx.return_value = True

        result = await self.redis_cache.get_or_fetch(
            "scheduled",
            SURFACE_ID,
            fetch_fn=self.fetch_fn,
            serialize_fn=self.serialize_fn,
            deserialize_fn=self.deserialize_fn,
        )

        assert result == ["item1", "item2"]
        self.fetch_fn.assert_called_once()

    @pytest.mark.asyncio
    async def test_lock_acquire_error_on_miss_raises_unavailable(self) -> None:
        """Raise CorpusCacheUnavailable when lock acquisition fails on miss."""
        self.mock_cache.get.return_value = None
        self.mock_cache.set_nx.side_effect = CacheAdapterError("lock error")

        with pytest.raises(CorpusCacheUnavailable):
            await self.redis_cache.get_or_fetch(
                "scheduled",
                SURFACE_ID,
                fetch_fn=self.fetch_fn,
                serialize_fn=self.serialize_fn,
                deserialize_fn=self.deserialize_fn,
            )

        self.fetch_fn.assert_not_called()

    @pytest.mark.asyncio
    async def test_lock_acquire_error_returns_stale_on_stale_hit(self) -> None:
        """Return stale data when lock acquisition fails on stale hit."""
        items_data = [{"v": "stale"}]
        self.mock_cache.get.return_value = _make_stale_envelope(items_data)
        self.mock_cache.set_nx.side_effect = CacheAdapterError("lock error")

        result = await self.redis_cache.get_or_fetch(
            "scheduled",
            SURFACE_ID,
            fetch_fn=self.fetch_fn,
            serialize_fn=self.serialize_fn,
            deserialize_fn=self.deserialize_fn,
        )

        assert result == ["stale"]
        self.fetch_fn.assert_not_called()

    @pytest.mark.asyncio
    async def test_backend_error_releases_lock(self) -> None:
        """Release the lock when the backend raises an error."""
        self.mock_cache.get.return_value = None
        self.mock_cache.set_nx.return_value = True
        self.fetch_fn.side_effect = Exception("API down")

        with pytest.raises(Exception, match="API down"):
            await self.redis_cache.get_or_fetch(
                "scheduled",
                SURFACE_ID,
                fetch_fn=self.fetch_fn,
                serialize_fn=self.serialize_fn,
                deserialize_fn=self.deserialize_fn,
            )

        self.mock_cache.delete.assert_called_once_with("curated:v1:lock:scheduled:NEW_TAB_EN_US")

    @pytest.mark.asyncio
    async def test_serialize_error_returns_items_and_releases_lock(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Return fetched items even when serialize_fn fails (best-effort cache write)."""
        self.mock_cache.get.return_value = None
        self.mock_cache.set_nx.return_value = True

        def bad_serialize(items: list) -> list[dict]:
            raise TypeError("cannot serialize")

        result = await self.redis_cache.get_or_fetch(
            "scheduled",
            SURFACE_ID,
            fetch_fn=self.fetch_fn,
            serialize_fn=bad_serialize,
            deserialize_fn=self.deserialize_fn,
        )

        assert result == ["item1", "item2"]
        self.mock_cache.delete.assert_called_once_with("curated:v1:lock:scheduled:NEW_TAB_EN_US")
        assert any("Serialization failed" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_deserialize_fn_error_on_fresh_hit_falls_through(self) -> None:
        """Fall through to backend when deserialize_fn raises on fresh cached data."""
        items_data = [{"v": "item1"}]
        self.mock_cache.get.return_value = _make_fresh_envelope(items_data)
        self.mock_cache.set_nx.return_value = True

        def bad_deserialize(data: list[dict]) -> list:
            raise ValueError("validation error")

        result = await self.redis_cache.get_or_fetch(
            "scheduled",
            SURFACE_ID,
            fetch_fn=self.fetch_fn,
            serialize_fn=self.serialize_fn,
            deserialize_fn=bad_deserialize,
        )

        assert result == ["item1", "item2"]
        self.fetch_fn.assert_called_once()

    @pytest.mark.asyncio
    async def test_stale_hit_lock_loser_deserialize_error_falls_through(self) -> None:
        """Fall through to backend when stale data can't be deserialized and lock is held."""
        items_data = [{"v": "stale"}]
        self.mock_cache.get.return_value = _make_stale_envelope(items_data)
        # First set_nx returns False (lock loser), second returns True (lock released)
        self.mock_cache.set_nx.side_effect = [False, True]

        def bad_deserialize(data: list[dict]) -> list:
            raise ValueError("schema changed")

        result = await self.redis_cache.get_or_fetch(
            "scheduled",
            SURFACE_ID,
            fetch_fn=self.fetch_fn,
            serialize_fn=self.serialize_fn,
            deserialize_fn=bad_deserialize,
        )

        assert result == ["item1", "item2"]
        self.fetch_fn.assert_called_once()

    @pytest.mark.asyncio
    async def test_stale_hit_deserialize_error_both_locks_fail_raises_unavailable(
        self,
    ) -> None:
        """Raise CorpusCacheUnavailable when stale deserialization fails and both locks fail."""
        items_data = [{"v": "stale"}]
        self.mock_cache.get.return_value = _make_stale_envelope(items_data)
        self.mock_cache.set_nx.return_value = False

        def bad_deserialize(data: list[dict]) -> list:
            raise ValueError("schema changed")

        with pytest.raises(CorpusCacheUnavailable):
            await self.redis_cache.get_or_fetch(
                "scheduled",
                SURFACE_ID,
                fetch_fn=self.fetch_fn,
                serialize_fn=self.serialize_fn,
                deserialize_fn=bad_deserialize,
            )

        self.fetch_fn.assert_not_called()

    @pytest.mark.asyncio
    async def test_redis_down_raises_unavailable(self) -> None:
        """Raise CorpusCacheUnavailable when Redis is completely unavailable."""
        self.mock_cache.get.side_effect = CacheAdapterError("connection refused")
        self.mock_cache.set_nx.side_effect = CacheAdapterError("connection refused")

        with pytest.raises(CorpusCacheUnavailable):
            await self.redis_cache.get_or_fetch(
                "scheduled",
                SURFACE_ID,
                fetch_fn=self.fetch_fn,
                serialize_fn=self.serialize_fn,
                deserialize_fn=self.deserialize_fn,
            )

        self.fetch_fn.assert_not_called()

    @pytest.mark.asyncio
    async def test_non_numeric_expires_at_treated_as_miss(self) -> None:
        """Treat an envelope with non-numeric expires_at as a cache miss."""
        self.mock_cache.get.return_value = orjson.dumps(
            {"expires_at": "not-a-number", "data": [{"v": "corrupted"}]}
        )
        self.mock_cache.set_nx.return_value = True

        result = await self.redis_cache.get_or_fetch(
            "scheduled",
            SURFACE_ID,
            fetch_fn=self.fetch_fn,
            serialize_fn=self.serialize_fn,
            deserialize_fn=self.deserialize_fn,
        )

        assert result == ["item1", "item2"]
        self.fetch_fn.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancelled_error_releases_lock(self) -> None:
        """Release the lock even when the fetch task is cancelled."""
        self.mock_cache.get.return_value = None
        self.mock_cache.set_nx.return_value = True

        async def cancelled_fetch() -> list:
            raise asyncio.CancelledError()

        with pytest.raises(asyncio.CancelledError):
            await self.redis_cache.get_or_fetch(
                "scheduled",
                SURFACE_ID,
                fetch_fn=cancelled_fetch,
                serialize_fn=self.serialize_fn,
                deserialize_fn=self.deserialize_fn,
            )

        self.mock_cache.delete.assert_called_once_with("curated:v1:lock:scheduled:NEW_TAB_EN_US")

    @pytest.mark.asyncio
    async def test_malformed_envelope_missing_key_falls_through(self) -> None:
        """Treat a JSON blob missing required keys as a cache miss."""
        self.mock_cache.get.return_value = orjson.dumps({"wrong_key": 123})
        self.mock_cache.set_nx.return_value = True

        result = await self.redis_cache.get_or_fetch(
            "scheduled",
            SURFACE_ID,
            fetch_fn=self.fetch_fn,
            serialize_fn=self.serialize_fn,
            deserialize_fn=self.deserialize_fn,
        )

        assert result == ["item1", "item2"]
        self.fetch_fn.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_list_is_cached(self) -> None:
        """Cache and return an empty list from the backend."""
        self.mock_cache.get.return_value = None
        self.mock_cache.set_nx.return_value = True
        self.fetch_fn.return_value = []

        result = await self.redis_cache.get_or_fetch(
            "scheduled",
            SURFACE_ID,
            fetch_fn=self.fetch_fn,
            serialize_fn=self.serialize_fn,
            deserialize_fn=self.deserialize_fn,
        )

        assert result == []
        self.mock_cache.set.assert_called_once()


class TestRedisCachedScheduledSurface:
    """Tests for the RedisCachedScheduledSurface wrapper."""

    def setup_method(self) -> None:
        """Set up mock backend and cache."""
        self.mock_backend = AsyncMock()
        self.mock_cache = AsyncMock()
        self.metrics_client = MagicMock(spec=aiodogstatsd.Client)
        self.wrapper = RedisCachedScheduledSurface(
            self.mock_backend, self.mock_cache, CONFIG, self.metrics_client
        )

    @pytest.mark.asyncio
    async def test_fresh_hit_returns_deserialized_items(self) -> None:
        """Return CorpusItem list from a fresh Redis cache hit."""
        item = generate_corpus_item()
        items_data = [item.model_dump(mode="json")]
        self.mock_cache.get.return_value = _make_fresh_envelope(items_data)

        result = await self.wrapper.fetch(SURFACE_ID, days_offset=0)

        assert len(result) == 1
        assert result[0].corpusItemId == "id"
        self.mock_backend.fetch.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_delegates_to_backend(self) -> None:
        """Delegate to the wrapped backend on cache miss."""
        item = generate_corpus_item()
        self.mock_cache.get.return_value = None
        self.mock_cache.set_nx.return_value = True
        self.mock_backend.fetch.return_value = [item]

        result = await self.wrapper.fetch(SURFACE_ID)

        assert len(result) == 1
        assert result[0].corpusItemId == "id"
        self.mock_backend.fetch.assert_called_once_with(SURFACE_ID, 0)


class TestRedisCachedSections:
    """Tests for the RedisCachedSections wrapper."""

    def setup_method(self) -> None:
        """Set up mock backend and cache."""
        self.mock_backend = AsyncMock()
        self.mock_cache = AsyncMock()
        self.metrics_client = MagicMock(spec=aiodogstatsd.Client)
        self.wrapper = RedisCachedSections(
            self.mock_backend, self.mock_cache, CONFIG, self.metrics_client
        )

    @pytest.mark.asyncio
    async def test_fresh_hit_returns_deserialized_sections(self) -> None:
        """Return CorpusSection list from a fresh Redis cache hit."""
        section = _make_corpus_section()
        sections_data = [section.model_dump(mode="json")]
        self.mock_cache.get.return_value = _make_fresh_envelope(sections_data)

        result = await self.wrapper.fetch(SURFACE_ID)

        assert len(result) == 1
        assert result[0].title == "Test Section"
        self.mock_backend.fetch.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_delegates_to_backend(self) -> None:
        """Delegate to the wrapped backend on cache miss."""
        section = _make_corpus_section()
        self.mock_cache.get.return_value = None
        self.mock_cache.set_nx.return_value = True
        self.mock_backend.fetch.return_value = [section]

        result = await self.wrapper.fetch(SURFACE_ID)

        assert len(result) == 1
        assert result[0].title == "Test Section"
        self.mock_backend.fetch.assert_called_once_with(SURFACE_ID)
