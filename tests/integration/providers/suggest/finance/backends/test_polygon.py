# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Integration tests for the Polygon backend module."""

import logging
import pytest
import pytest_asyncio

from logging import LogRecord, ERROR
from pytest import LogCaptureFixture
from typing import Any, AsyncGenerator
from merino.configs import settings
from tests.types import FilterCaplogFixture
from httpx import AsyncClient
from pytest_mock import MockerFixture
from unittest.mock import AsyncMock
from redis.asyncio import Redis
from testcontainers.core.waiting_utils import wait_for_logs
from testcontainers.redis import AsyncRedisContainer

from merino.cache.redis import RedisAdapter
from merino.exceptions import CacheAdapterError

from merino.providers.suggest.finance.backends.protocol import TickerSnapshot
from merino.providers.suggest.finance.backends.polygon import PolygonBackend
from merino.providers.suggest.finance.backends.polygon.utils import generate_cache_key_for_ticker

logger = logging.getLogger(__name__)

URL_SINGLE_TICKER_SNAPSHOT = settings.polygon.url_single_ticker_snapshot
URL_SINGLE_TICKER_OVERVIEW = settings.polygon.url_single_ticker_overview
TICKER_TTL_SEC = settings.providers.polygon.cache_ttls.ticker_ttl_sec


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


@pytest.fixture(name="polygon_parameters")
def fixture_polygon_parameters(
    mocker: MockerFixture, statsd_mock: Any, redis_client: Redis
) -> dict[str, Any]:
    """Create constructor parameters for Polygon backend module."""
    return {
        "api_key": "api_key",
        "metrics_client": statsd_mock,
        "http_client": mocker.AsyncMock(spec=AsyncClient),
        "metrics_sample_rate": 1,
        "url_param_api_key": "apiKey",
        "url_single_ticker_snapshot": URL_SINGLE_TICKER_SNAPSHOT,
        "url_single_ticker_overview": URL_SINGLE_TICKER_OVERVIEW,
        "gcs_uploader": mocker.MagicMock(),
        "gcs_uploader_v2": mocker.MagicMock(),
        "cache": RedisAdapter(redis_client),
        "ticker_ttl_sec": TICKER_TTL_SEC,
    }


@pytest.fixture(name="polygon_factory")
def fixture_polygon_factory(mocker: MockerFixture, statsd_mock: Any, redis_client: Redis):
    """Return factory fixture to create Polygon backend parameters with overrides."""

    def _polygon_parameters(**overrides: Any) -> dict[str, Any]:
        params = {
            "api_key": "api_key",
            "metrics_client": statsd_mock,
            "http_client": mocker.AsyncMock(spec=AsyncClient),
            "metrics_sample_rate": 1,
            "url_param_api_key": "apiKey",
            "url_single_ticker_snapshot": URL_SINGLE_TICKER_SNAPSHOT,
            "url_single_ticker_overview": URL_SINGLE_TICKER_OVERVIEW,
            "gcs_uploader": mocker.MagicMock(),
            "cache": RedisAdapter(redis_client),
            "ticker_ttl_sec": TICKER_TTL_SEC,
        }
        params.update(overrides)
        return params

    return _polygon_parameters


@pytest.fixture(name="polygon")
def fixture_polygon(
    polygon_parameters: dict[str, Any],
    mocker: MockerFixture,
) -> PolygonBackend:
    """Create a Polygon backend module object."""
    mock_filemanager = mocker.MagicMock()
    mocker.patch(
        "merino.providers.suggest.finance.backends.polygon.backend.PolygonFilemanager",
        return_value=mock_filemanager,
    )
    return PolygonBackend(**polygon_parameters)


@pytest.fixture(name="ticker_snapshot_AAPL")
def fixture_ticker_snapshot_AAPL() -> TickerSnapshot:
    """Create a ticker snapshot object for AAPL."""
    # these values are based on the above single_ticker_snapshot_response fixture.
    return TickerSnapshot(
        ticker="AAPL",
        last_trade_price="120.47",
        todays_change_percent="0.82",
    )


@pytest.fixture(name="ticker_snapshot_NFLX")
def fixture_ticker_snapshot_NFLX() -> TickerSnapshot:
    """Create a ticker snapshot object for AAPL."""
    # these values are based on the above single_ticker_snapshot_response fixture.
    return TickerSnapshot(
        ticker="NFLX",
        last_trade_price="555.01",
        todays_change_percent="1.82",
    )


async def set_redis_key_expiry(
    redis_client: Redis, keys_and_expiry: list[tuple[str, int]]
) -> None:
    """Set redis cache key expiry (TTL seconds)."""
    for key, ttl in keys_and_expiry:
        await redis_client.expire(key, ttl)


@pytest.mark.asyncio
async def test_get_snapshots_from_cache_success(
    mocker: MockerFixture,
    polygon: PolygonBackend,
    ticker_snapshot_AAPL: TickerSnapshot,
    ticker_snapshot_NFLX,
) -> None:
    """Test that get_snapshots_from_cache method successfully returns the correct snapshots with TTLs."""
    expected = [
        (ticker_snapshot_AAPL, TICKER_TTL_SEC),
        (ticker_snapshot_NFLX, TICKER_TTL_SEC),
    ]

    # write to cache
    await polygon.store_snapshots_in_cache([ticker_snapshot_AAPL, ticker_snapshot_NFLX])

    # call backend method
    actual = await polygon.get_snapshots_from_cache(["AAPL", "NFLX"])

    assert actual is not None
    assert actual == expected

    assert actual[0] == expected[0]
    assert actual[1] == expected[1]

    # `get_snapshots` should not make a network API call on a cache hit.
    spy = mocker.spy(polygon.http_client, "get")

    snapshots = await polygon.get_snapshots(["AAPL", "NFLX"])

    spy.assert_not_called()
    assert snapshots == [snapshot for snapshot, _ttl in expected]


@pytest.mark.asyncio
async def test_get_snapshots_from_cache_returns_empty_list(
    polygon: PolygonBackend, ticker_snapshot_AAPL: TickerSnapshot, ticker_snapshot_NFLX
) -> None:
    """Test that get_snapshots_from_cache method returns an empty list for keys not found."""
    # write to cache
    await polygon.store_snapshots_in_cache([ticker_snapshot_AAPL, ticker_snapshot_NFLX])

    # call backend method with non-existent keys
    actual = await polygon.get_snapshots_from_cache(["TSLA", "QQQ"])

    assert actual is not None
    assert actual == []


@pytest.mark.asyncio
async def test_get_snapshots_from_cache_raises_cache_error(
    polygon: PolygonBackend,
    ticker_snapshot_AAPL: TickerSnapshot,
    mocker: MockerFixture,
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
) -> None:
    """Test that get_snapshots_from_cache method raises a CacheAdapterError and error logs."""
    # Set the log level
    caplog.set_level(ERROR)

    # patch the polygon back cache with a mock that throws on run_script()
    redis_error_mock = mocker.patch.object(polygon.cache, "run_script", new_callable=AsyncMock)
    redis_error_mock.side_effect = CacheAdapterError("test cache error")

    # get from cache
    actual = await polygon.get_snapshots_from_cache(["AAPL"])

    # capture error log
    records: list[LogRecord] = filter_caplog(
        caplog.records, "merino.providers.suggest.finance.backends.polygon.backend"
    )

    assert len(records) == 1
    assert records[0].message.startswith("Failed to fetch snapshots from Redis: test cache error")
    assert actual == []


@pytest.mark.asyncio
async def test_refresh_ticker_cache_entries_success(
    polygon_factory,
    ticker_snapshot_AAPL: TickerSnapshot,
    ticker_snapshot_NFLX,
    redis_client: Redis,
    mocker,
) -> None:
    """Test that refresh_ticker_cache_entries method successfully writes snapshots to cache with new TTL."""
    polygon = PolygonBackend(**polygon_factory(cache=RedisAdapter(redis_client)))

    # Mocking the get_snapshots method to return AAPL and NFLX snapshots fixtures for 2 calls.
    get_snapshots_mock = mocker.patch.object(
        polygon, "get_snapshots", new_callable=mocker.AsyncMock
    )
    get_snapshots_mock.return_value = [ticker_snapshot_AAPL, ticker_snapshot_NFLX]

    expected = [(ticker_snapshot_AAPL, TICKER_TTL_SEC), (ticker_snapshot_NFLX, TICKER_TTL_SEC)]

    # write to cache (this method writes with the default 300 sec TTL)
    await polygon.store_snapshots_in_cache([ticker_snapshot_AAPL, ticker_snapshot_NFLX])

    # manually modify the TTL for the above cache entries to 100 instead of 300
    cache_keys = []
    for key in ["AAPL", "NFLX"]:
        cache_keys.append(generate_cache_key_for_ticker(key))
    await set_redis_key_expiry(redis_client, [(cache_keys[0], 100), (cache_keys[1], 100)])

    # refresh the cache entries -- this should reset the TTL to 300
    # forcing the await here otherwise this task finishes after test execution
    await polygon.refresh_ticker_cache_entries(["AAPL", "NFLX"], await_store=True)

    actual = await polygon.get_snapshots_from_cache(["AAPL", "NFLX"])

    assert actual is not None
    assert actual == expected

    assert actual[0] == expected[0]
    assert actual[1] == expected[1]
