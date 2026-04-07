"""Integration tests for the Redis L2 corpus cache with a real Redis instance."""

import logging

import aiodogstatsd
import pytest
import pytest_asyncio
from typing import AsyncGenerator
from unittest.mock import MagicMock

from redis.asyncio import Redis
from testcontainers.core.waiting_utils import wait_for_logs
from testcontainers.redis import AsyncRedisContainer

from merino.cache.redis import RedisAdapter
from merino.curated_recommendations.corpus_backends.protocol import SurfaceId
from merino.curated_recommendations.corpus_backends.redis_cache import (
    CorpusCacheConfig,
    _RedisCorpusCache,
)
from merino.exceptions import CorpusCacheUnavailable

logger = logging.getLogger(__name__)

CONFIG = CorpusCacheConfig(
    soft_ttl_sec=120,
    hard_ttl_sec=600,
    lock_ttl_sec=30,
    key_prefix="curated:v1",
)

SURFACE_ID = SurfaceId.NEW_TAB_EN_US


@pytest.fixture(scope="module")
def redis_container() -> AsyncRedisContainer:
    """Create and return a docker container for Redis."""
    logger.info("Starting up redis container")
    container = AsyncRedisContainer().start()

    delay = wait_for_logs(container, "Server initialized")
    logger.info(f"\n Redis server started with delay: {delay} seconds")

    yield container

    container.stop()
    logger.info("\n Redis container stopped")


@pytest_asyncio.fixture(name="redis_client")
async def fixture_redis_client(
    redis_container: AsyncRedisContainer,
) -> AsyncGenerator[Redis, None]:
    """Create and return a Redis client, flushed after each test."""
    client = await redis_container.get_async_client()

    yield client

    await client.flushall()


@pytest.fixture(name="cache")
def fixture_cache(redis_client: Redis) -> RedisAdapter:
    """Create a RedisAdapter wrapping the test Redis client."""
    return RedisAdapter(redis_client)


@pytest.fixture(name="redis_cache")
def fixture_redis_cache(cache: RedisAdapter) -> _RedisCorpusCache:
    """Create a _RedisCorpusCache with a real Redis backend."""
    metrics = MagicMock(spec=aiodogstatsd.Client)
    return _RedisCorpusCache(cache, CONFIG, metrics)


class TestHappyPath:
    """Integration tests for the Redis corpus cache happy path."""

    @pytest.mark.asyncio
    async def test_cache_miss_then_hit(self, redis_cache: _RedisCorpusCache) -> None:
        """First call fetches from backend and writes to Redis. Second call returns cached data."""
        fetch_count = 0

        async def fetch_fn() -> list[str]:
            nonlocal fetch_count
            fetch_count += 1
            return ["item1", "item2"]

        serialize_fn = lambda items: [{"v": i} for i in items]
        deserialize_fn = lambda data: [d["v"] for d in data]

        # First call: cache miss → fetches from backend, writes to Redis
        result1 = await redis_cache.get_or_fetch(
            "scheduled",
            SURFACE_ID,
            fetch_fn=fetch_fn,
            serialize_fn=serialize_fn,
            deserialize_fn=deserialize_fn,
        )
        assert result1 == ["item1", "item2"]
        assert fetch_count == 1

        # Second call: cache hit → returns from Redis without calling backend
        result2 = await redis_cache.get_or_fetch(
            "scheduled",
            SURFACE_ID,
            fetch_fn=fetch_fn,
            serialize_fn=serialize_fn,
            deserialize_fn=deserialize_fn,
        )
        assert result2 == ["item1", "item2"]
        assert fetch_count == 1  # Not incremented — served from cache

    @pytest.mark.asyncio
    async def test_distributed_lock_prevents_concurrent_fetches(
        self, redis_cache: _RedisCorpusCache
    ) -> None:
        """Only one caller fetches when multiple hit a cache miss concurrently."""
        import asyncio

        fetch_count = 0

        async def slow_fetch_fn() -> list[str]:
            nonlocal fetch_count
            fetch_count += 1
            await asyncio.sleep(0.1)
            return ["item1"]

        serialize_fn = lambda items: [{"v": i} for i in items]
        deserialize_fn = lambda data: [d["v"] for d in data]

        # Launch two concurrent get_or_fetch calls on the same key
        results = await asyncio.gather(
            redis_cache.get_or_fetch(
                "scheduled",
                SURFACE_ID,
                fetch_fn=slow_fetch_fn,
                serialize_fn=serialize_fn,
                deserialize_fn=deserialize_fn,
            ),
            redis_cache.get_or_fetch(
                "scheduled",
                SURFACE_ID,
                fetch_fn=slow_fetch_fn,
                serialize_fn=serialize_fn,
                deserialize_fn=deserialize_fn,
            ),
            return_exceptions=True,
        )

        # One should succeed with data, the other either succeeds (retry hit)
        # or raises CorpusCacheUnavailable (retry miss)
        successes = [r for r in results if isinstance(r, list)]
        errors = [r for r in results if isinstance(r, CorpusCacheUnavailable)]
        assert len(successes) + len(errors) == 2
        assert len(successes) >= 1
        for s in successes:
            assert s == ["item1"]

        # Only one fetch should have occurred (the lock winner)
        assert fetch_count == 1
