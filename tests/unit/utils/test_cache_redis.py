# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the cron.py module."""

import pytest
from pytest_mock import MockerFixture

from redis.asyncio import Redis

from merino.cache.redis import create_redis_clients, RedisAdapter


@pytest.mark.asyncio
async def test_adapter_in_standalone_mode(mocker: MockerFixture) -> None:
    """Test `RedisAdapter` for the standalone mode."""
    spy = mocker.spy(Redis, "aclose")
    adapter: RedisAdapter = RedisAdapter(
        *create_redis_clients(
            primary="redis://localhost:6379",
            replica="redis://localhost:6379",
            max_connections=1,
            db=0,
        )
    )

    assert adapter.primary is adapter.replica

    await adapter.close()

    spy.assert_called_once()
