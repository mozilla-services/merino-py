# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Integration tests for the Yelp backend module."""

# import datetime
import orjson
import logging

from logging import LogRecord
from typing import Any, AsyncGenerator, cast
from unittest.mock import AsyncMock

import pytest

from pytest import LogCaptureFixture
import pytest_asyncio
from httpx import AsyncClient
from pytest_mock import MockerFixture
from redis.asyncio import Redis
from merino.cache.redis import RedisAdapter
from merino.exceptions import CacheAdapterError

from testcontainers.core.waiting_utils import wait_for_logs
from testcontainers.redis import AsyncRedisContainer

from tests.types import FilterCaplogFixture

from merino.providers.suggest.yelp.backends.yelp import YelpBackend

logger = logging.getLogger(__name__)

TEST_CACHE_ERROR = "test cache error"

@pytest.fixture(name="yelp_parameters")
def fixture_yelp_parameters(mocker: MockerFixture, statsd_mock: Any) -> dict[str, Any]:
    """TODO"""
    return {
        "api_key": "test-api-key",
        "http_client": mocker.AsyncMock(spec=AsyncClient),
        "url_business_search": "test-url-bus-search",
        "cache_ttl_sec": 86400,
        "cache": None,
        "metrics_client": statsd_mock,
    }


@pytest.fixture(name="yelp")
def fixture_yelp_backend(yelp_parameters) -> YelpBackend:
    """Return a YelpBackend object with cache set to None."""
    return YelpBackend(**yelp_parameters)


# TODO define fixtures for cached data (binary json) to assert on


@pytest.fixture(scope="module")
def redis_container() -> AsyncRedisContainer:
    """Create and return a docker container for Redis. Tear it down after all the tests have
    finished running
    """
    logger.info("Starting up redis container")
    container = AsyncRedisContainer().start()

    # wait for the container to start and emit logs
    delay = wait_for_logs(container, "Server initialized")
    logger.info(f"\n Redis server started with delay: {delay} seconds on port: {container.port}")

    yield container

    container.stop()
    logger.info("\n Redis container stopped")


@pytest_asyncio.fixture(name="redis_client")
async def fixture_redis_client(
    redis_container: AsyncRedisContainer,
) -> AsyncGenerator[Redis, None]:
    """Create and return a Redis client"""
    client = await redis_container.get_async_client()

    yield client

    await client.flushall()


async def set_redis_keys(redis_client: Redis, keys_and_values: list[tuple]) -> None:
    """Set redis cache keys and values after flushing the db"""
    for key, value, expiry in keys_and_values:
        await redis_client.set(key, value, ex=expiry)


@pytest.mark.asyncio
async def test_get_from_cache(
    redis_client: Redis,
    statsd_mock: Any,
    yelp: YelpBackend,
) -> None:
    """Test that we can get the weather report from cache with forecast and current conditions
    having a valid TTL
    """
    # Override the cache with a non-None value. Default cache for the fixture is set to None.
    yelp.cache = RedisAdapter(redis_client)

    # Test data
    search_term = "starbucks near me"
    location = "Seattle"

    # get cache keys
    cache_key = yelp.generate_cache_key(search_term, location)
    expected_cached_data = b'{"test": "test_value"}'

    # use the above cache_key with a test value and default yelp backend ttl.
    keys_values_expiry = [
        (cache_key, expected_cached_data, yelp.cache_ttl_sec),
    ]
    await set_redis_keys(redis_client, keys_values_expiry)

    actual_cached_data = await yelp.get_from_cache(cache_key)

    assert actual_cached_data is not None
    assert actual_cached_data == orjson.loads(expected_cached_data)

    metrics_timeit_called = [call_arg[0][0] for call_arg in statsd_mock.timeit.call_args_list]
    assert metrics_timeit_called == ["yelp.cache.fetch"]

    metrics_increment_called = [
        call_arg[0][0] for call_arg in statsd_mock.increment.call_args_list
    ]
    assert metrics_increment_called == ["yelp.cache.hit"]


# TODO add more tests to cover these use cases(make sure you're asserting on logger and statsd metrics as well):
# when cache is set to None
# when cache is empty and we request something from it
# when it throws CacheAdapterError (see accuweather integration tests on how to test for this)
# when it throws Exception


@pytest.mark.asyncio
async def test_get_from_none_cache(
    redis_client: Redis,
    statsd_mock: Any,
    yelp: YelpBackend,
) -> None:
    """Test handling a response from a None cache"""
    yelp.cache = None

    search_term = "starbucks near me"
    location = "Seattle"

    cache_key = yelp.generate_cache_key(search_term, location)
    expected_cached_data = b'{"test": "test_value"}'

    keys_values_expiry = [
        (cache_key, expected_cached_data, yelp.cache_ttl_sec),
    ]
    await set_redis_keys(redis_client, keys_values_expiry)

    actual_cached_data = await yelp.get_from_cache(cache_key)

    assert actual_cached_data is None

    metrics_timeit_called = [call_arg[0][0] for call_arg in statsd_mock.timeit.call_args_list]
    assert metrics_timeit_called == []

    metrics_increment_called = [
        call_arg[0][0] for call_arg in statsd_mock.increment.call_args_list
    ]
    assert metrics_increment_called == []


@pytest.mark.asyncio
async def test_get_from_empty_cache(
    redis_client: Redis,
    statsd_mock: Any,
    yelp: YelpBackend,
) -> None:
    """Test handling a response from an empty cache"""
    yelp.cache = RedisAdapter(redis_client)

    search_term = "starbucks near me"
    location = "Seattle"

    cache_key = yelp.generate_cache_key(search_term, location)

    actual_cached_data = await yelp.get_from_cache(cache_key)

    assert actual_cached_data is None

    metrics_timeit_called = [call_arg[0][0] for call_arg in statsd_mock.timeit.call_args_list]
    assert metrics_timeit_called == []

    metrics_increment_called = [
        call_arg[0][0] for call_arg in statsd_mock.increment.call_args_list
    ]
    assert metrics_increment_called == []


@pytest.mark.asyncio
async def test_get_from_cache_with_cache_adapter_error(
    redis_client: Redis,
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
    statsd_mock: Any,
    yelp: YelpBackend,
    mocker: MockerFixture,
) -> None:
    """Test handling the CacheAdapterError exception"""
    yelp.cache = RedisAdapter(redis_client)

    search_term = "starbucks near me"
    location = "Seattle"

    cache_key = yelp.generate_cache_key(search_term, location)

    redis_error_mock = mocker.patch.object(yelp.cache, "get", new_callable=AsyncMock)
    redis_error_mock.side_effect = CacheAdapterError(TEST_CACHE_ERROR)

    client_mock: AsyncMock = cast(AsyncMock, yelp.http_client)

    # This will fail because nothing is being raised
    # with pytest.raises(Exception): # TODO update with yelp error
    #     _ = await yelp.get_from_cache(cache_key)

    await yelp.get_from_cache(cache_key)

    records: list[LogRecord] = filter_caplog(
        caplog.records, "merino.providers.suggest.yelp.backends.yelp"
    )

    client_mock.get.assert_not_called()

    assert len(records) == 1
    assert records[0].message.startswith(f"Yelp cache get error for {cache_key}")

    metrics_timeit_called = [call_arg[0][0] for call_arg in statsd_mock.timeit.call_args_list]
    assert metrics_timeit_called == []

    metrics_increment_called = [
        call_arg[0][0] for call_arg in statsd_mock.increment.call_args_list
    ]
    assert metrics_increment_called == ["yelp.cache.error"]


@pytest.mark.asyncio
async def test_get_from_cache_with_general_cache_error(
    redis_client: Redis,
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
    statsd_mock: Any,
    yelp: YelpBackend,
    mocker: MockerFixture,
) -> None:
    """Test handling general cache exceptions"""
    yelp.cache = RedisAdapter(redis_client)

    search_term = "starbucks near me"
    location = "Seattle"

    cache_key = yelp.generate_cache_key(search_term, location)

    redis_error_mock = mocker.patch.object(yelp.cache, "get", new_callable=AsyncMock)
    redis_error_mock.side_effect = Exception(TEST_CACHE_ERROR)

    client_mock: AsyncMock = cast(AsyncMock, yelp.http_client)

    await yelp.get_from_cache(cache_key)

    records: list[LogRecord] = filter_caplog(
        caplog.records, "merino.providers.suggest.yelp.backends.yelp"
    )

    client_mock.get.assert_not_called()

    assert len(records) == 1
    assert records[0].message.startswith(f"Yelp cache decode error for {cache_key}")

    metrics_timeit_called = [call_arg[0][0] for call_arg in statsd_mock.timeit.call_args_list]
    assert metrics_timeit_called == []

    metrics_increment_called = [
        call_arg[0][0] for call_arg in statsd_mock.increment.call_args_list
    ]
    assert metrics_increment_called == ["yelp.cache.decode_error"]
