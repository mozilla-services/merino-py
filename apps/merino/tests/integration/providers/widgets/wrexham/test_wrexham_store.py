# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Integration tests for the Wrexham widget Redis store"""

from datetime import UTC, datetime, timedelta
from typing import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from freezegun import freeze_time
from redis.asyncio import Redis
from testcontainers.community.redis import AsyncRedisContainer
from testcontainers.core.wait_strategies import LogMessageWaitStrategy

from merino.cache.redis import RedisAdapter
from merino.providers.widgets.wrexham.protocol import (
    Competition,
    Match,
    MatchStatus,
    Standing,
    Team,
)
from merino.providers.widgets.wrexham.store import (
    LIVE_MATCHES_KEY,
    STANDINGS_KEY,
    WrexhamStore,
    fixtures_key,
)
from tests.integration.fixtures.redis import REDIS_IMAGE

NOW = datetime(2026, 11, 2, 15, 30, tzinfo=UTC)
FIXTURES_TTL = timedelta(hours=3)
CHAMPIONSHIP_ID = 34


def _team(team_id: int) -> Team:
    """Build a team for tests."""
    return Team(id=team_id, name=f"Team {team_id}", logo_url="https://example.com/logo.png")


def _match(match_id: int, status: MatchStatus) -> Match:
    """Build a match that hasn't started yet, or is in progress."""
    in_progress = status == MatchStatus.InProgress
    return Match(
        id=match_id,
        competition=Competition(id=CHAMPIONSHIP_ID, name="EFL Championship"),
        kickoff=datetime(2026, 11, 2, 15, tzinfo=UTC),
        home_team=_team(1),
        away_team=_team(2),
        period=None,
        status=status,
        clock="25" if in_progress else None,
        home_score=0 if in_progress else None,
        away_score=0 if in_progress else None,
        home_penalty_score=None,
        away_penalty_score=None,
        updated_at=NOW,
    )


@pytest.fixture(scope="module")
def redis_container() -> Generator[AsyncRedisContainer, None, None]:
    """Start a Redis container for the module's tests."""
    container = (
        AsyncRedisContainer(REDIS_IMAGE)
        .waiting_for(LogMessageWaitStrategy("Server initialized"))
        .start()
    )
    yield container
    container.stop()


@pytest_asyncio.fixture(name="redis_client")
async def fixture_redis_client(
    redis_container: AsyncRedisContainer,
) -> AsyncGenerator[Redis, None]:
    """Return a Redis client, flushing the database after each test."""
    client = await redis_container.get_async_client()
    yield client
    await client.flushall()


@pytest.fixture(name="store")
def fixture_store(redis_client: Redis) -> WrexhamStore:
    """Return a store backed by the real Redis adapter."""
    return WrexhamStore(
        cache=RedisAdapter(redis_client),
        fixtures_ttl=FIXTURES_TTL,
        live_matches_ttl=timedelta(minutes=10),
        standings_ttl=timedelta(hours=6),
    )


@freeze_time(NOW)
@pytest.mark.asyncio
async def test_round_trips_each_data_type(store: WrexhamStore, redis_client: Redis) -> None:
    """Fixtures, live matches and standings round-trip through Redis under their keys."""
    fixtures = [_match(1, MatchStatus.Scheduled), _match(2, MatchStatus.Scheduled)]
    live = [_match(3, MatchStatus.InProgress)]
    standings = [
        Standing(position=1, team=_team(1), played=14, goal_difference=5, points=30),
        Standing(position=2, team=_team(2), played=14, goal_difference=3, points=28),
    ]

    await store.write_fixtures(CHAMPIONSHIP_ID, fixtures)
    await store.write_live_matches(live)
    await store.write_standings(standings)

    assert await store.read_fixtures(CHAMPIONSHIP_ID) == (fixtures, NOW)
    assert await store.read_live_matches() == (live, NOW)
    assert await store.read_standings() == (standings, NOW)
    assert set(await redis_client.keys("wrexham:v1:*")) == {
        fixtures_key(CHAMPIONSHIP_ID).encode(),
        LIVE_MATCHES_KEY.encode(),
        STANDINGS_KEY.encode(),
    }


@pytest.mark.asyncio
async def test_sets_an_expiry_on_written_data(store: WrexhamStore, redis_client: Redis) -> None:
    """Written data expires after the configured time."""
    await store.write_fixtures(CHAMPIONSHIP_ID, [])

    ttl_seconds = await redis_client.ttl(fixtures_key(CHAMPIONSHIP_ID))

    assert FIXTURES_TTL.total_seconds() - 60 < ttl_seconds <= FIXTURES_TTL.total_seconds()
