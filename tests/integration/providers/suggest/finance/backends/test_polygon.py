# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Integration tests for the Polygon backend module."""

import logging
from typing import Any, AsyncGenerator
from merino.configs import settings

import pytest
import pytest_asyncio
from httpx import AsyncClient
from pytest_mock import MockerFixture
from redis.asyncio import Redis
from testcontainers.core.waiting_utils import wait_for_logs
from testcontainers.redis import AsyncRedisContainer

from merino.cache.redis import RedisAdapter

from merino.providers.suggest.finance.backends.protocol import TickerSnapshot
from merino.providers.suggest.finance.backends.polygon import PolygonBackend

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
        "cache": RedisAdapter(redis_client),
        "ticker_ttl_sec": TICKER_TTL_SEC,
    }


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


@pytest.mark.asyncio
async def test_get_snapshots_from_cache_success(
    polygon: PolygonBackend, ticker_snapshot_AAPL: TickerSnapshot, ticker_snapshot_NFLX
) -> None:
    """Test that get_snapshots_from_cache method successfully returns the correct snapshots with TTLs."""
    expected = [(ticker_snapshot_AAPL, TICKER_TTL_SEC), (ticker_snapshot_NFLX, TICKER_TTL_SEC)]

    # write to cache
    await polygon.store_snapshots_in_cache([ticker_snapshot_AAPL, ticker_snapshot_NFLX])

    # call backend method
    actual = await polygon.get_snapshots_from_cache(["AAPL", "NFLX"])

    assert actual is not None
    assert actual == expected

    assert actual[0] == expected[0]
    assert actual[1] == expected[1]


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


# TODO add test for cache adapter error
# TODO add test for validation error
