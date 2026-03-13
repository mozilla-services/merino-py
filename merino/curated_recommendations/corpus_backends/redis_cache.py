"""Redis L2 cache for corpus backends with distributed stale-while-revalidate."""

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import timedelta
from typing import Awaitable, Callable, TypeVar

import orjson

from merino.cache.protocol import CacheAdapter
from merino.curated_recommendations.corpus_backends.protocol import (
    CorpusItem,
    CorpusSection,
    ScheduledSurfaceProtocol,
    SectionsProtocol,
    SurfaceId,
)
from merino.exceptions import CacheAdapterError

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass(frozen=True)
class CorpusCacheConfig:
    """Configuration for the Redis corpus cache layer.

    Attributes:
        soft_ttl_sec: Seconds before a cached entry is considered stale. One pod revalidates
            while others continue to serve the stale value.
        hard_ttl_sec: Seconds before Redis evicts the key entirely. Safety net.
        lock_ttl_sec: Seconds before a distributed revalidation lock auto-expires.
        key_prefix: Prefix for all Redis keys. Bump the version on schema changes.
    """

    soft_ttl_sec: int
    hard_ttl_sec: int
    lock_ttl_sec: int
    key_prefix: str

    def __post_init__(self) -> None:
        """Validate that TTL values are consistent and positive."""
        if self.soft_ttl_sec <= 0:
            raise ValueError(f"soft_ttl_sec ({self.soft_ttl_sec}) must be positive")
        if self.hard_ttl_sec <= 0:
            raise ValueError(f"hard_ttl_sec ({self.hard_ttl_sec}) must be positive")
        if self.lock_ttl_sec <= 0:
            raise ValueError(f"lock_ttl_sec ({self.lock_ttl_sec}) must be positive")
        if self.hard_ttl_sec <= self.soft_ttl_sec:
            raise ValueError(
                f"hard_ttl_sec ({self.hard_ttl_sec}) must be greater than "
                f"soft_ttl_sec ({self.soft_ttl_sec})"
            )
        if self.hard_ttl_sec <= self.lock_ttl_sec:
            raise ValueError(
                f"hard_ttl_sec ({self.hard_ttl_sec}) must be greater than "
                f"lock_ttl_sec ({self.lock_ttl_sec})"
            )


def _build_data_key(
    config: CorpusCacheConfig, backend_type: str, surface_id: str, *extra: str
) -> str:
    """Build the Redis key for cached corpus data."""
    parts = [config.key_prefix, backend_type, surface_id, *extra]
    return ":".join(parts)


def _build_lock_key(
    config: CorpusCacheConfig, backend_type: str, surface_id: str, *extra: str
) -> str:
    """Build the Redis key for the distributed revalidation lock."""
    parts = [config.key_prefix, "lock", backend_type, surface_id, *extra]
    return ":".join(parts)


def _serialize_envelope(data: list[dict], soft_ttl_sec: int) -> bytes:
    """Serialize data with an expiration timestamp into a cache envelope."""
    envelope = {
        "expires_at": time.time() + soft_ttl_sec,
        "data": data,
    }
    return orjson.dumps(envelope)


def _deserialize_envelope(raw: bytes) -> tuple[float, list[dict]]:
    """Deserialize a cache envelope, returning (expires_at, data)."""
    envelope = orjson.loads(raw)
    return envelope["expires_at"], envelope["data"]


class _RedisCorpusCache:
    """Shared Redis cache logic for corpus backends.

    Implements distributed stale-while-revalidate: when the cached value is stale,
    one pod acquires a lock and revalidates while others serve stale data.
    """

    def __init__(self, cache: CacheAdapter, config: CorpusCacheConfig) -> None:
        self._cache = cache
        self._config = config

    async def get_or_fetch(
        self,
        backend_type: str,
        surface_id: str,
        *extra: str,
        fetch_fn: Callable[[], Awaitable[list[T]]],
        serialize_fn: Callable[[list[T]], list[dict]],
        deserialize_fn: Callable[[list[dict]], list[T]],
    ) -> list[T]:
        """Check Redis, returning cached data or fetching from the backend.

        Args:
            backend_type: Type identifier for key namespacing (e.g. "scheduled", "sections").
            surface_id: Surface ID value for the cache key.
            *extra: Additional key segments (e.g. days_offset).
            fetch_fn: Async callable that fetches fresh data from the backend.
            serialize_fn: Converts typed models to dicts for Redis storage.
            deserialize_fn: Converts dicts from Redis back to typed models.
        """
        data_key = _build_data_key(self._config, backend_type, surface_id, *extra)
        lock_key = _build_lock_key(self._config, backend_type, surface_id, *extra)
        # Try reading from Redis
        cached = await self._redis_get(data_key)
        if cached is not None:
            try:
                expires_at, items_data = cached
                is_fresh = time.time() < expires_at
            except TypeError:
                # expires_at is not numeric (corrupted envelope)
                logger.warning(
                    "Invalid expires_at in corpus cache key %s", data_key, exc_info=True
                )
                is_fresh = False
                items_data = None

            if is_fresh and items_data is not None:
                try:
                    return deserialize_fn(items_data)
                except Exception:
                    logger.warning(
                        "Deserialization failed for corpus cache key %s",
                        data_key,
                        exc_info=True,
                    )
                    # Fall through to revalidation/fetch below
            elif items_data is not None:
                # Stale — try to revalidate
                if await self._try_acquire_lock(lock_key):
                    return await self._revalidate(data_key, lock_key, fetch_fn, serialize_fn)
                try:
                    return deserialize_fn(items_data)
                except Exception:
                    logger.warning(
                        "Deserialization of stale data failed for corpus cache key %s",
                        data_key,
                        exc_info=True,
                    )

        # Cache miss — try to acquire lock and fetch
        if await self._try_acquire_lock(lock_key):
            return await self._revalidate(data_key, lock_key, fetch_fn, serialize_fn)
        # Another pod is populating; wait briefly then retry Redis
        await asyncio.sleep(0.1)
        cached = await self._redis_get(data_key)
        if cached is not None:
            _, items_data = cached
            if items_data is not None:
                try:
                    return deserialize_fn(items_data)
                except Exception:
                    logger.warning(
                        "Deserialization failed on retry for corpus cache key %s",
                        data_key,
                        exc_info=True,
                    )
        # Last resort: Redis may be down or lock holder slow. Fetch directly
        # so the L2 cache never degrades availability below what L1+API provide.
        logger.warning("Falling back to direct fetch for %s", data_key)
        return await fetch_fn()

    async def _revalidate(
        self,
        data_key: str,
        lock_key: str,
        fetch_fn: Callable[[], Awaitable[list[T]]],
        serialize_fn: Callable[[list[T]], list[dict]],
    ) -> list[T]:
        """Fetch from the backend, write to Redis, and release the lock.

        Uses try/finally to ensure the lock is released even on cancellation
        (asyncio.CancelledError is a BaseException, not caught by except Exception).
        """
        try:
            items = await fetch_fn()
            # Cache write is best-effort: don't lose fetched items on serialize or write failure.
            try:
                serialized = serialize_fn(items)
            except Exception:
                logger.warning(
                    "Serialization failed for corpus cache key %s", data_key, exc_info=True
                )
            else:
                await self._redis_set(data_key, serialized)
            return items
        finally:
            await self._release_lock(lock_key)

    async def _redis_get(self, key: str) -> tuple[float, list[dict]] | None:
        """Read and deserialize from Redis. Returns None on any error."""
        try:
            raw = await self._cache.get(key)
            if raw is None:
                return None
            return _deserialize_envelope(raw)
        except CacheAdapterError:
            logger.warning("Redis read error for corpus cache key %s", key, exc_info=True)
            return None
        except (orjson.JSONDecodeError, KeyError, TypeError):
            logger.warning(
                "Redis deserialization error for corpus cache key %s",
                key,
                exc_info=True,
            )
            return None

    async def _redis_set(self, key: str, data: list[dict]) -> None:
        """Serialize and write to Redis. Logs on error without raising."""
        try:
            value = _serialize_envelope(data, self._config.soft_ttl_sec)
            await self._cache.set(key, value, ttl=timedelta(seconds=self._config.hard_ttl_sec))
        except Exception:
            logger.warning("Redis write error for corpus cache key %s", key, exc_info=True)

    async def _try_acquire_lock(self, lock_key: str) -> bool:
        """Attempt to acquire a distributed lock via SET NX EX."""
        try:
            return await self._cache.set_nx(lock_key, self._config.lock_ttl_sec)
        except CacheAdapterError:
            logger.warning("Redis lock acquire error for %s", lock_key, exc_info=True)
            return False

    async def _release_lock(self, lock_key: str) -> None:
        """Release the distributed lock by deleting the key.

        Note: This uses unconditional DELETE rather than owner-aware release
        (compare-and-delete via Lua script). If revalidation exceeds lock_ttl_sec
        (30s default), another pod's lock could be deleted. The consequence is at
        most one extra redundant API call, not a stampede, because the SWR pattern
        ensures other pods serve stale/cached data regardless of lock state.
        """
        try:
            await self._cache.delete(lock_key)
        except CacheAdapterError:
            logger.warning("Redis lock release error for %s", lock_key, exc_info=True)


class RedisCachedScheduledSurface(ScheduledSurfaceProtocol):
    """Redis L2 cache wrapper for ScheduledSurfaceBackend.

    Checks Redis before hitting the Corpus API. Uses distributed SWR:
    when the cached value is stale, one pod acquires a lock and revalidates
    while others continue to serve stale data.
    """

    def __init__(
        self,
        backend: ScheduledSurfaceProtocol,
        cache: CacheAdapter,
        config: CorpusCacheConfig,
    ) -> None:
        self._backend = backend
        self._redis_cache = _RedisCorpusCache(cache, config)

    async def fetch(self, surface_id: SurfaceId, days_offset: int = 0) -> list[CorpusItem]:
        """Fetch corpus items, checking Redis L2 cache first."""
        return await self._redis_cache.get_or_fetch(
            "scheduled",
            surface_id.value,
            str(days_offset),
            fetch_fn=lambda: self._backend.fetch(surface_id, days_offset),
            serialize_fn=lambda items: [item.model_dump(mode="json") for item in items],
            deserialize_fn=lambda data: [CorpusItem.model_validate(d) for d in data],
        )


class RedisCachedSections(SectionsProtocol):
    """Redis L2 cache wrapper for SectionsBackend.

    Same distributed SWR pattern as RedisCachedScheduledSurface.
    """

    def __init__(
        self,
        backend: SectionsProtocol,
        cache: CacheAdapter,
        config: CorpusCacheConfig,
    ) -> None:
        self._backend = backend
        self._redis_cache = _RedisCorpusCache(cache, config)

    async def fetch(self, surface_id: SurfaceId) -> list[CorpusSection]:
        """Fetch corpus sections, checking Redis L2 cache first."""
        return await self._redis_cache.get_or_fetch(
            "sections",
            surface_id.value,
            fetch_fn=lambda: self._backend.fetch(surface_id),
            serialize_fn=lambda sections: [s.model_dump(mode="json") for s in sections],
            deserialize_fn=lambda data: [CorpusSection.model_validate(d) for d in data],
        )
