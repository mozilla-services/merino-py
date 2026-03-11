"""Unit tests for the Redis L2 corpus cache layer."""

import time
from unittest.mock import AsyncMock

import orjson
import pytest

from merino.curated_recommendations.corpus_backends.protocol import (
    CorpusItem,
    CorpusSection,
    CreateSource,
    SurfaceId,
)
from merino.curated_recommendations.corpus_backends.redis_cache import (
    CorpusCacheConfig,
    RedisCachedScheduledSurface,
    RedisCachedSections,
    _RedisCorpusCache,
    _build_data_key,
    _build_lock_key,
    _deserialize_envelope,
    _serialize_envelope,
)
from merino.exceptions import CacheAdapterError

SURFACE_ID = SurfaceId.NEW_TAB_EN_US

CONFIG = CorpusCacheConfig(
    soft_ttl_sec=120,
    hard_ttl_sec=600,
    lock_ttl_sec=30,
    key_prefix="curated:v1",
)


class TestCorpusCacheConfig:
    """Tests for CorpusCacheConfig validation."""

    def test_valid_config(self) -> None:
        """Accept valid TTL ordering."""
        config = CorpusCacheConfig(
            soft_ttl_sec=120, hard_ttl_sec=600, lock_ttl_sec=30, key_prefix="test"
        )
        assert config.soft_ttl_sec == 120

    def test_hard_ttl_must_exceed_soft_ttl(self) -> None:
        """Reject hard_ttl_sec <= soft_ttl_sec."""
        with pytest.raises(ValueError, match="hard_ttl_sec.*must be greater than.*soft_ttl_sec"):
            CorpusCacheConfig(
                soft_ttl_sec=600, hard_ttl_sec=120, lock_ttl_sec=30, key_prefix="test"
            )

    def test_hard_ttl_must_exceed_lock_ttl(self) -> None:
        """Reject hard_ttl_sec <= lock_ttl_sec."""
        with pytest.raises(ValueError, match="hard_ttl_sec.*must be greater than.*lock_ttl_sec"):
            CorpusCacheConfig(soft_ttl_sec=10, hard_ttl_sec=20, lock_ttl_sec=30, key_prefix="test")

    @pytest.mark.parametrize(
        "soft,hard,lock",
        [
            (0, 600, 30),
            (120, 0, 30),
            (120, 600, 0),
            (-1, 600, 30),
        ],
        ids=["zero_soft", "zero_hard", "zero_lock", "negative_soft"],
    )
    def test_ttl_values_must_be_positive(self, soft: int, hard: int, lock: int) -> None:
        """Reject zero or negative TTL values."""
        with pytest.raises(ValueError, match="must be positive"):
            CorpusCacheConfig(
                soft_ttl_sec=soft, hard_ttl_sec=hard, lock_ttl_sec=lock, key_prefix="test"
            )


def _make_corpus_item(**overrides: object) -> CorpusItem:
    """Create a CorpusItem with sensible defaults."""
    defaults = {
        "corpusItemId": "abc-123",
        "url": "https://example.com/article",
        "title": "Test Article",
        "excerpt": "A test excerpt",
        "topic": None,
        "publisher": "Example Publisher",
        "isTimeSensitive": False,
        "imageUrl": "https://example.com/image.jpg",
    }
    defaults.update(overrides)
    return CorpusItem.model_validate(defaults)


def _make_corpus_section(**overrides: object) -> CorpusSection:
    """Create a CorpusSection with sensible defaults."""
    defaults = {
        "sectionItems": [_make_corpus_item()],
        "title": "Test Section",
        "externalId": "test-section",
        "createSource": CreateSource.ML,
    }
    defaults.update(overrides)
    return CorpusSection.model_validate(defaults)


def _make_fresh_envelope(items_data: list[dict], soft_ttl_sec: int = 120) -> bytes:
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

    def test_build_data_key_scheduled(self) -> None:
        """Build a data key for a scheduled surface with days_offset."""
        key = _build_data_key(CONFIG, "scheduled", "NEW_TAB_EN_US", "0")
        assert key == "curated:v1:scheduled:NEW_TAB_EN_US:0"

    def test_build_data_key_sections(self) -> None:
        """Build a data key for sections."""
        key = _build_data_key(CONFIG, "sections", "NEW_TAB_EN_US")
        assert key == "curated:v1:sections:NEW_TAB_EN_US"

    def test_build_lock_key(self) -> None:
        """Build a lock key with 'lock' segment inserted."""
        key = _build_lock_key(CONFIG, "scheduled", "NEW_TAB_EN_US", "0")
        assert key == "curated:v1:lock:scheduled:NEW_TAB_EN_US:0"


class TestEnvelope:
    """Tests for envelope serialization and deserialization."""

    def test_roundtrip(self) -> None:
        """Serialize and deserialize an envelope."""
        data = [{"corpusItemId": "abc", "title": "Hello"}]
        raw = _serialize_envelope(data, soft_ttl_sec=120)
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
        self.redis_cache = _RedisCorpusCache(self.mock_cache, CONFIG)
        self.fetch_fn = AsyncMock(return_value=["item1", "item2"])
        self.serialize_fn = lambda items: [{"v": i} for i in items]
        self.deserialize_fn = lambda data: [d["v"] for d in data]

    @pytest.mark.asyncio
    async def test_fresh_hit_returns_cached_data(self) -> None:
        """Return deserialized data on a fresh Redis hit without calling fetch_fn."""
        items_data = [{"v": "item1"}, {"v": "item2"}]
        self.mock_cache.get.return_value = _make_fresh_envelope(items_data)

        result = await self.redis_cache.get_or_fetch(
            "data:key", "lock:key", self.fetch_fn, self.serialize_fn, self.deserialize_fn
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
            "data:key", "lock:key", self.fetch_fn, self.serialize_fn, self.deserialize_fn
        )

        assert result == ["item1", "item2"]
        self.fetch_fn.assert_called_once()
        self.mock_cache.set.assert_called_once()
        self.mock_cache.delete.assert_called_once_with("lock:key")

    @pytest.mark.asyncio
    async def test_stale_hit_lock_loser_returns_stale(self) -> None:
        """Return stale data when another pod holds the lock."""
        items_data = [{"v": "stale"}]
        self.mock_cache.get.return_value = _make_stale_envelope(items_data)
        self.mock_cache.set_nx.return_value = False

        result = await self.redis_cache.get_or_fetch(
            "data:key", "lock:key", self.fetch_fn, self.serialize_fn, self.deserialize_fn
        )

        assert result == ["stale"]
        self.fetch_fn.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_lock_winner_fetches(self) -> None:
        """Fetch from backend on cache miss when lock is acquired."""
        self.mock_cache.get.return_value = None
        self.mock_cache.set_nx.return_value = True

        result = await self.redis_cache.get_or_fetch(
            "data:key", "lock:key", self.fetch_fn, self.serialize_fn, self.deserialize_fn
        )

        assert result == ["item1", "item2"]
        self.fetch_fn.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_miss_lock_loser_falls_through(self) -> None:
        """Fall through to backend when cache misses and lock is held."""
        self.mock_cache.get.return_value = None
        self.mock_cache.set_nx.return_value = False

        result = await self.redis_cache.get_or_fetch(
            "data:key", "lock:key", self.fetch_fn, self.serialize_fn, self.deserialize_fn
        )

        assert result == ["item1", "item2"]
        self.fetch_fn.assert_called_once()

    @pytest.mark.asyncio
    async def test_redis_read_error_falls_through(self) -> None:
        """Fall through to backend when Redis read fails."""
        self.mock_cache.get.side_effect = CacheAdapterError("connection refused")
        self.mock_cache.set_nx.return_value = True

        result = await self.redis_cache.get_or_fetch(
            "data:key", "lock:key", self.fetch_fn, self.serialize_fn, self.deserialize_fn
        )

        assert result == ["item1", "item2"]
        self.fetch_fn.assert_called_once()

    @pytest.mark.asyncio
    async def test_redis_write_error_does_not_raise(self) -> None:
        """Continue normally when Redis write fails after fetching."""
        self.mock_cache.get.return_value = None
        self.mock_cache.set_nx.return_value = True
        self.mock_cache.set.side_effect = CacheAdapterError("write failed")

        result = await self.redis_cache.get_or_fetch(
            "data:key", "lock:key", self.fetch_fn, self.serialize_fn, self.deserialize_fn
        )

        assert result == ["item1", "item2"]

    @pytest.mark.asyncio
    async def test_deserialization_error_falls_through(self) -> None:
        """Treat corrupted Redis data as a cache miss."""
        self.mock_cache.get.return_value = b"not valid json"
        self.mock_cache.set_nx.return_value = True

        result = await self.redis_cache.get_or_fetch(
            "data:key", "lock:key", self.fetch_fn, self.serialize_fn, self.deserialize_fn
        )

        assert result == ["item1", "item2"]
        self.fetch_fn.assert_called_once()

    @pytest.mark.asyncio
    async def test_lock_acquire_error_falls_through_on_miss(self) -> None:
        """Fall through to backend when lock acquisition fails on cache miss."""
        self.mock_cache.get.return_value = None
        self.mock_cache.set_nx.side_effect = CacheAdapterError("lock error")

        result = await self.redis_cache.get_or_fetch(
            "data:key", "lock:key", self.fetch_fn, self.serialize_fn, self.deserialize_fn
        )

        assert result == ["item1", "item2"]
        self.fetch_fn.assert_called_once()

    @pytest.mark.asyncio
    async def test_lock_acquire_error_returns_stale_on_stale_hit(self) -> None:
        """Return stale data when lock acquisition fails on stale hit."""
        items_data = [{"v": "stale"}]
        self.mock_cache.get.return_value = _make_stale_envelope(items_data)
        self.mock_cache.set_nx.side_effect = CacheAdapterError("lock error")

        result = await self.redis_cache.get_or_fetch(
            "data:key", "lock:key", self.fetch_fn, self.serialize_fn, self.deserialize_fn
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
                "data:key",
                "lock:key",
                self.fetch_fn,
                self.serialize_fn,
                self.deserialize_fn,
            )

        self.mock_cache.delete.assert_called_once_with("lock:key")

    @pytest.mark.asyncio
    async def test_serialize_error_returns_items_and_releases_lock(self) -> None:
        """Return fetched items even when serialize_fn fails (best-effort cache write)."""
        self.mock_cache.get.return_value = None
        self.mock_cache.set_nx.return_value = True

        def bad_serialize(items: list) -> list[dict]:
            raise TypeError("cannot serialize")

        result = await self.redis_cache.get_or_fetch(
            "data:key",
            "lock:key",
            self.fetch_fn,
            bad_serialize,
            self.deserialize_fn,
        )

        assert result == ["item1", "item2"]
        self.mock_cache.delete.assert_called_once_with("lock:key")

    @pytest.mark.asyncio
    async def test_deserialize_fn_error_on_fresh_hit_falls_through(self) -> None:
        """Fall through to backend when deserialize_fn raises on fresh cached data."""
        items_data = [{"v": "item1"}]
        self.mock_cache.get.return_value = _make_fresh_envelope(items_data)
        self.mock_cache.set_nx.return_value = True

        def bad_deserialize(data: list[dict]) -> list:
            raise ValueError("validation error")

        result = await self.redis_cache.get_or_fetch(
            "data:key", "lock:key", self.fetch_fn, self.serialize_fn, bad_deserialize
        )

        assert result == ["item1", "item2"]
        self.fetch_fn.assert_called_once()

    @pytest.mark.asyncio
    async def test_malformed_envelope_missing_key_falls_through(self) -> None:
        """Treat a JSON blob missing required keys as a cache miss."""
        self.mock_cache.get.return_value = orjson.dumps({"wrong_key": 123})
        self.mock_cache.set_nx.return_value = True

        result = await self.redis_cache.get_or_fetch(
            "data:key", "lock:key", self.fetch_fn, self.serialize_fn, self.deserialize_fn
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
            "data:key", "lock:key", self.fetch_fn, self.serialize_fn, self.deserialize_fn
        )

        assert result == []
        self.mock_cache.set.assert_called_once()


class TestRedisCachedScheduledSurface:
    """Tests for the RedisCachedScheduledSurface wrapper."""

    def setup_method(self) -> None:
        """Set up mock backend and cache."""
        self.mock_backend = AsyncMock()
        self.mock_cache = AsyncMock()
        self.wrapper = RedisCachedScheduledSurface(self.mock_backend, self.mock_cache, CONFIG)

    @pytest.mark.asyncio
    async def test_fresh_hit_returns_deserialized_items(self) -> None:
        """Return CorpusItem list from a fresh Redis cache hit."""
        item = _make_corpus_item()
        items_data = [item.model_dump(mode="json")]
        self.mock_cache.get.return_value = _make_fresh_envelope(items_data)

        result = await self.wrapper.fetch(SURFACE_ID, days_offset=0)

        assert len(result) == 1
        assert result[0].corpusItemId == "abc-123"
        self.mock_backend.fetch.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_delegates_to_backend(self) -> None:
        """Delegate to the wrapped backend on cache miss."""
        item = _make_corpus_item()
        self.mock_cache.get.return_value = None
        self.mock_cache.set_nx.return_value = True
        self.mock_backend.fetch.return_value = [item]

        result = await self.wrapper.fetch(SURFACE_ID)

        assert len(result) == 1
        assert result[0].corpusItemId == "abc-123"
        self.mock_backend.fetch.assert_called_once_with(SURFACE_ID, 0)

    @pytest.mark.asyncio
    async def test_days_offset_included_in_key(self) -> None:
        """Include days_offset in the Redis key to differentiate cache entries."""
        self.mock_cache.get.return_value = None
        self.mock_cache.set_nx.return_value = True
        self.mock_backend.fetch.return_value = [_make_corpus_item()]

        await self.wrapper.fetch(SURFACE_ID, days_offset=-1)

        # Verify the key includes the days_offset
        set_call = self.mock_cache.set.call_args
        key = set_call[0][0]
        assert ":-1" in key


class TestRedisCachedSections:
    """Tests for the RedisCachedSections wrapper."""

    def setup_method(self) -> None:
        """Set up mock backend and cache."""
        self.mock_backend = AsyncMock()
        self.mock_cache = AsyncMock()
        self.wrapper = RedisCachedSections(self.mock_backend, self.mock_cache, CONFIG)

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
