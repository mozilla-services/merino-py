"""Redis L2 cache for corpus backends with distributed stale-while-revalidate."""

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import timedelta
from typing import Awaitable, Callable, Literal, TypeVar

import aiodogstatsd
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


class CorpusCacheUnavailable(Exception):
    """Raised when the corpus cache cannot serve data.

    Triggers include: cold miss with lock held or retry exhausted.
    The API layer translates this to HTTP 503.
    """

    pass


BackendType = Literal["scheduled", "sections"]


@dataclass(frozen=True)
class CorpusCacheConfig:
    """Configuration for the Redis corpus cache layer.

    Attributes:
        soft_ttl_sec: Seconds before a cached entry is considered stale. One pod revalidates
            while others continue to serve the stale value.
        hard_ttl_sec: Seconds before Redis evicts the key entirely. Safety net.
        lock_ttl_sec: Seconds before a distributed revalidation lock auto-expires.
        key_prefix: Prefix for all Redis keys. Bump the version (e.g. v1 → v2) on
            breaking schema changes so stale data from the old format is not deserialized.
    """

    soft_ttl_sec: int
    hard_ttl_sec: int
    lock_ttl_sec: int
    key_prefix: str


def _build_data_key(
    config: CorpusCacheConfig, backend_type: BackendType, surface_id: SurfaceId
) -> str:
    """Build the Redis key for cached corpus data."""
    return ":".join([config.key_prefix, backend_type, surface_id.value])


def _build_lock_key(
    config: CorpusCacheConfig, backend_type: BackendType, surface_id: SurfaceId
) -> str:
    """Build the Redis key for the distributed revalidation lock."""
    return ":".join([config.key_prefix, "lock", backend_type, surface_id.value])


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

    No circuit breaker: the L1 in-memory cache's asyncio.Lock already limits Redis
    traffic to one coroutine per cache entry per pod. Redis errors surface as
    CorpusCacheUnavailable (HTTP 503) only on cold starts; in steady state, L1
    serves stale data and the background revalidation task absorbs any Redis errors.
    """

    def __init__(
        self,
        cache: CacheAdapter,
        config: CorpusCacheConfig,
        metrics_client: aiodogstatsd.Client,
    ) -> None:
        self._cache = cache
        self._config = config
        self._metrics = metrics_client

    async def get_or_fetch(
        self,
        backend_type: BackendType,
        surface_id: SurfaceId,
        *,
        fetch_fn: Callable[[], Awaitable[list[T]]],
        serialize_fn: Callable[[list[T]], list[dict]],
        deserialize_fn: Callable[[list[dict]], list[T]],
    ) -> list[T]:
        """Check Redis, returning cached data or fetching from the backend.

        Args:
            backend_type: Type identifier for key namespacing.
            surface_id: Surface ID enum for the cache key.
            fetch_fn: Async callable that fetches fresh data from the backend.
            serialize_fn: Converts typed models to dicts for Redis storage.
            deserialize_fn: Converts dicts from Redis back to typed models.
        """
        data_key = _build_data_key(self._config, backend_type, surface_id)
        lock_key = _build_lock_key(self._config, backend_type, surface_id)
        # Try reading from Redis
        cached = await self._redis_get(data_key)
        if cached is not None:
            try:
                expires_at, items_data = cached
                is_fresh = time.time() < expires_at
            except TypeError:
                # expires_at is not numeric (corrupted envelope)
                logger.error("Invalid expires_at in corpus cache key %s", data_key, exc_info=True)
                is_fresh = False
                items_data = None

            if is_fresh and items_data is not None:
                try:
                    result = deserialize_fn(items_data)
                    self._metrics.increment("corpus_cache.hit")
                    return result
                except Exception:
                    logger.error(
                        "Deserialization failed for corpus cache key %s",
                        data_key,
                        exc_info=True,
                    )
                    # Fall through to revalidation/fetch below
            elif items_data is not None:
                # Stale — try to revalidate
                self._metrics.increment("corpus_cache.stale")
                if await self._try_acquire_lock(lock_key):
                    return await self._revalidate(data_key, lock_key, fetch_fn, serialize_fn)
                try:
                    return deserialize_fn(items_data)
                except Exception:
                    logger.error(
                        "Deserialization of stale data failed for corpus cache key %s",
                        data_key,
                        exc_info=True,
                    )

        # Cache miss — try to acquire lock and fetch
        self._metrics.increment("corpus_cache.miss")
        if await self._try_acquire_lock(lock_key):
            return await self._revalidate(data_key, lock_key, fetch_fn, serialize_fn)
        # Another pod is populating; wait for it to finish (P95 API latency is ~217ms)
        await asyncio.sleep(0.5)
        cached = await self._redis_get(data_key)
        if cached is not None:
            _, items_data = cached
            if items_data is not None:
                try:
                    return deserialize_fn(items_data)
                except Exception:
                    logger.error(
                        "Deserialization failed on retry for corpus cache key %s",
                        data_key,
                        exc_info=True,
                    )
        # No data available and another pod holds the lock. Signal the API layer
        # to return 503 so connections don't pile up waiting for the lock holder.
        raise CorpusCacheUnavailable(f"No data available for {data_key}")

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
                logger.error(
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
            logger.error("Redis read error for corpus cache key %s", key, exc_info=True)
            return None
        except (orjson.JSONDecodeError, KeyError, TypeError):
            logger.error(
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
            logger.error("Redis write error for corpus cache key %s", key, exc_info=True)

    async def _try_acquire_lock(self, lock_key: str) -> bool:
        """Attempt to acquire a distributed lock via SET NX EX."""
        try:
            result = await self._cache.set_nx(lock_key, self._config.lock_ttl_sec)
            return result
        except CacheAdapterError:
            logger.error("Redis lock acquire error for %s", lock_key, exc_info=True)
            return False

    async def _release_lock(self, lock_key: str) -> None:
        """Release the distributed lock by deleting the key.

        Note: This uses unconditional DELETE rather than owner-aware release
        (compare-and-delete via Lua script). If revalidation exceeds lock_ttl_sec
        (30s default), another pod's lock could be deleted. The consequence is at
        most one extra redundant API call, not a stampede, because the stale-while-revalidate pattern
        ensures other pods serve stale/cached data regardless of lock state.
        """
        try:
            await self._cache.delete(lock_key)
        except CacheAdapterError:
            logger.error("Redis lock release error for %s", lock_key, exc_info=True)


class RedisCachedScheduledSurface(ScheduledSurfaceProtocol):
    """Redis L2 cache wrapper for ScheduledSurfaceBackend.

    Checks Redis before hitting the Corpus API. Uses distributed stale-while-revalidate:
    one pod acquires a lock and revalidates while others serve stale data.
    """

    def __init__(
        self,
        backend: ScheduledSurfaceProtocol,
        cache: CacheAdapter,
        config: CorpusCacheConfig,
        metrics_client: aiodogstatsd.Client,
    ) -> None:
        self._backend = backend
        self._redis_cache = _RedisCorpusCache(cache, config, metrics_client)

    async def fetch(self, surface_id: SurfaceId, days_offset: int = 0) -> list[CorpusItem]:
        """Fetch corpus items, checking Redis L2 cache first."""
        return await self._redis_cache.get_or_fetch(
            "scheduled",
            surface_id,
            fetch_fn=lambda: self._backend.fetch(surface_id, days_offset),
            serialize_fn=lambda items: [item.model_dump(mode="json") for item in items],
            deserialize_fn=lambda data: [CorpusItem.model_validate(d) for d in data],
        )


class RedisCachedSections(SectionsProtocol):
    """Redis L2 cache wrapper for SectionsBackend.

    Same distributed stale-while-revalidate pattern as RedisCachedScheduledSurface.
    """

    def __init__(
        self,
        backend: SectionsProtocol,
        cache: CacheAdapter,
        config: CorpusCacheConfig,
        metrics_client: aiodogstatsd.Client,
    ) -> None:
        self._backend = backend
        self._redis_cache = _RedisCorpusCache(cache, config, metrics_client)

    async def fetch(self, surface_id: SurfaceId) -> list[CorpusSection]:
        """Fetch corpus sections, checking Redis L2 cache first."""
        return await self._redis_cache.get_or_fetch(
            "sections",
            surface_id,
            fetch_fn=lambda: self._backend.fetch(surface_id),
            serialize_fn=lambda sections: [s.model_dump(mode="json") for s in sections],
            deserialize_fn=lambda data: [CorpusSection.model_validate(d) for d in data],
        )
