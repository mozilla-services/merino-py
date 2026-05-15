# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Integration tests for WCS against a real Redis instance."""

import logging
from typing import AsyncGenerator, cast

import pytest
import pytest_asyncio
from httpx import AsyncClient
from pytest_mock import MockerFixture
from redis.asyncio import Redis
from testcontainers.core.waiting_utils import wait_for_logs
from testcontainers.redis import AsyncRedisContainer

from merino.cache.redis import RedisAdapter
from merino.configs import settings
from merino.providers.suggest.sports.backends.sportsdata.common.sports import WCS

logger = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def redis_container() -> AsyncRedisContainer:
    """Spin up a Redis container for the duration of this test module."""
    logger.info("Starting up redis container")
    container = AsyncRedisContainer().start()
    wait_for_logs(container, "Server initialized")
    yield container
    container.stop()


@pytest_asyncio.fixture(name="redis_client")
async def fixture_redis_client(
    redis_container: AsyncRedisContainer,
) -> AsyncGenerator[Redis, None]:
    """Return an async Redis client connected to the container."""
    client = await redis_container.get_async_client()
    yield client
    await client.flushall()


@pytest.fixture(name="mock_client")
def fixture_mock_client(mocker: MockerFixture) -> AsyncClient:
    """Return a mocked AsyncClient (load_areas only uses it as a pass-through)."""
    return cast(AsyncClient, mocker.Mock(spec=AsyncClient))


@pytest.mark.asyncio
async def test_wcs_load_areas_stores_areas_in_redis(
    mock_client: AsyncClient,
    redis_client: Redis,
    mocker: MockerFixture,
) -> None:
    """Regression test: load_areas must not crash when a country has no alias entry.

    Mocks the `/Areas` response with one country present in `country_alias` (TUR)
    and one absent from it (USA). If aliases=None is in the hset payload,
    Redis rejects with `DataError: Invalid input of type: 'NoneType'`.
    """
    areas_payload = [
        {"AreaId": 196, "CountryCode": "TUR", "Name": "Türkiye", "Competitions": []},
        {"AreaId": 203, "CountryCode": "USA", "Name": "United States", "Competitions": []},
    ]
    mocker.patch(
        "merino.providers.suggest.sports.backends.sportsdata.common.sports.get_data",
        side_effect=[areas_payload],
    )

    sport = WCS(settings=settings.providers.sports, cache=RedisAdapter(redis_client))

    await sport.load_areas(mock_client)

    tur = await redis_client.hgetall(f"{sport.cache_prefix}:area:196")
    usa = await redis_client.hgetall(f"{sport.cache_prefix}:area:203")
    assert tur[b"code"] == b"TUR"
    assert usa[b"code"] == b"USA"
    assert b"aliases" in tur
    assert b"aliases" not in usa
