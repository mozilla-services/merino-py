# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the Wrexham widget Redis store."""

from datetime import UTC, datetime, timedelta

import orjson
import pytest
from freezegun import freeze_time
from pytest import LogCaptureFixture
from pytest_mock import MockerFixture

from merino.cache.none import NoCacheAdapter
from merino.exceptions import CacheAdapterError
from merino.providers.widgets.wrexham.protocol import (
    Competition,
    Match,
    MatchPeriod,
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
from tests.types import FilterCaplogFixture

NOW = datetime(2026, 11, 2, 15, 30, tzinfo=UTC)
FIXTURES_TTL = timedelta(hours=3)
LIVE_MATCHES_TTL = timedelta(minutes=10)
STANDINGS_TTL = timedelta(hours=6)
CHAMPIONSHIP_ID = 34
FA_CUP_ID = 27


def _team(team_id: int) -> Team:
    """Build a team for testing."""
    return Team(id=team_id, name=f"Team {team_id}", logo_url="https://example.com/logo.png")


def _match(match_id: int, competition_id: int, status: MatchStatus = MatchStatus.Final) -> Match:
    """Build a match for testing."""
    finished = status == MatchStatus.Final
    return Match(
        id=match_id,
        competition=Competition(id=competition_id, name=f"Competition {competition_id}"),
        kickoff=datetime(2026, 10, 31, 15, tzinfo=UTC),
        home_team=_team(1),
        away_team=_team(2),
        period=MatchPeriod.Regular if finished else None,
        status=status,
        clock=None,
        home_score=2 if finished else None,
        away_score=1 if finished else None,
        home_penalty_score=None,
        away_penalty_score=None,
        updated_at=datetime(2026, 10, 31, 17, tzinfo=UTC),
    )


def _standing(position: int) -> Standing:
    """Build a table row for tests."""
    return Standing(
        position=position, team=_team(position), played=14, goal_difference=0, points=20
    )


class FakeCache(NoCacheAdapter):
    """In-memory stand-in for a cache adapter that records expiry times."""

    def __init__(self) -> None:
        self.values: dict[str, bytes] = {}
        self.ttls: dict[str, timedelta | None] = {}

    async def get(self, key: str) -> bytes | None:
        """Return the stored value, or None."""
        return self.values.get(key)

    async def set(
        self, key: str, value: bytes | str, ttl: timedelta | None = None, nx: bool = False
    ) -> None:
        """Store a value and record its expiry."""
        self.values[key] = value.encode() if isinstance(value, str) else value
        self.ttls[key] = ttl


@pytest.fixture(name="cache")
def fixture_cache() -> FakeCache:
    """Return an empty in-memory cache."""
    return FakeCache()


@pytest.fixture(name="store")
def fixture_store(cache: FakeCache) -> WrexhamStore:
    """Return a store backed by the in-memory cache."""
    return WrexhamStore(
        cache=cache,
        fixtures_ttl=FIXTURES_TTL,
        live_matches_ttl=LIVE_MATCHES_TTL,
        standings_ttl=STANDINGS_TTL,
    )


def test_key_names_use_the_versioned_prefix() -> None:
    """Every key uses the `wrexham:v1:` prefix, with one fixtures key per competition."""
    assert fixtures_key(34) == "wrexham:v1:fixtures:34"
    assert fixtures_key(27) == "wrexham:v1:fixtures:27"
    assert LIVE_MATCHES_KEY == "wrexham:v1:live"
    assert STANDINGS_KEY == "wrexham:v1:standings"


@freeze_time(NOW)
@pytest.mark.asyncio
async def test_fixtures_round_trip_per_competition(store: WrexhamStore, cache: FakeCache) -> None:
    """Fixtures are written and read per competition, with the fetch time and expiry."""
    championship = [_match(1, CHAMPIONSHIP_ID), _match(2, CHAMPIONSHIP_ID)]
    fa_cup = [_match(3, FA_CUP_ID)]

    await store.write_fixtures(CHAMPIONSHIP_ID, championship)
    await store.write_fixtures(FA_CUP_ID, fa_cup)

    assert await store.read_fixtures(CHAMPIONSHIP_ID) == (championship, NOW)
    assert await store.read_fixtures(FA_CUP_ID) == (fa_cup, NOW)
    assert cache.ttls[fixtures_key(CHAMPIONSHIP_ID)] == FIXTURES_TTL


@freeze_time(NOW)
@pytest.mark.asyncio
async def test_live_matches_round_trip(store: WrexhamStore, cache: FakeCache) -> None:
    """Live matches are written and read under one key, with the fetch time and expiry."""
    live = [_match(4, CHAMPIONSHIP_ID, status=MatchStatus.InProgress)]

    await store.write_live_matches(live)

    assert await store.read_live_matches() == (live, NOW)
    assert cache.ttls[LIVE_MATCHES_KEY] == LIVE_MATCHES_TTL


@freeze_time(NOW)
@pytest.mark.asyncio
async def test_empty_live_matches_round_trip(store: WrexhamStore) -> None:
    """An empty list of live matches is stored as empty, not as missing data."""
    await store.write_live_matches([])

    assert await store.read_live_matches() == ([], NOW)


@freeze_time(NOW)
@pytest.mark.asyncio
async def test_standings_round_trip(store: WrexhamStore, cache: FakeCache) -> None:
    """The table is written and read with its fetch time and expiry."""
    standings = [_standing(1), _standing(2), _standing(3)]

    await store.write_standings(standings)

    assert await store.read_standings() == (standings, NOW)
    assert cache.ttls[STANDINGS_KEY] == STANDINGS_TTL


@freeze_time(NOW)
@pytest.mark.asyncio
async def test_written_value_holds_the_fetch_time_and_data(
    store: WrexhamStore, cache: FakeCache
) -> None:
    """The stored JSON holds the fetch time next to the data."""
    await store.write_live_matches([])

    assert orjson.loads(cache.values[LIVE_MATCHES_KEY]) == {
        "fetched_at": "2026-11-02T15:30:00Z",
        "data": [],
    }


@pytest.mark.asyncio
async def test_read_accepts_a_utc_offset_written_as_plus_zero(
    store: WrexhamStore, cache: FakeCache
) -> None:
    """A fetch time written as `+00:00` instead of `Z` is still read correctly."""
    cache.values[LIVE_MATCHES_KEY] = b'{"fetched_at": "2026-11-02T15:30:00+00:00", "data": []}'

    assert await store.read_live_matches() == ([], NOW)


@pytest.mark.asyncio
async def test_read_returns_none_when_nothing_is_stored(store: WrexhamStore) -> None:
    """Reading data that was never written returns None."""
    assert await store.read_fixtures(CHAMPIONSHIP_ID) is None
    assert await store.read_live_matches() is None
    assert await store.read_standings() is None


@pytest.mark.parametrize(
    "raw",
    [
        b"not json",
        b'{"data": []}',
        b'{"fetched_at": "yesterday", "data": []}',
        b'{"fetched_at": "2026-11-02T15:30:00+00:00", "data": {"not": "a table"}}',
        b"[]",
        b'{"fetched_at": "2026-11-02T15:30:00", "data": []}',
    ],
    ids=[
        "invalid_json",
        "missing_fetched_at",
        "invalid_fetched_at",
        "invalid_data",
        "not_an_object",
        "fetched_at_without_timezone",
    ],
)
@pytest.mark.asyncio
async def test_read_returns_none_and_logs_when_data_cant_be_parsed(
    store: WrexhamStore,
    cache: FakeCache,
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
    raw: bytes,
) -> None:
    """A stored value that can't be parsed is logged and treated as missing."""
    cache.values[STANDINGS_KEY] = raw

    assert await store.read_standings() is None

    records = filter_caplog(caplog.records, "merino.providers.widgets.wrexham.store")
    assert len(records) == 1
    assert records[0].message == "Could not parse stored Wrexham data"
    assert records[0].__dict__["key"] == STANDINGS_KEY


@pytest.mark.asyncio
async def test_read_raises_cache_errors(mocker: MockerFixture) -> None:
    """Cache backend errors are raised to the caller."""
    cache = mocker.AsyncMock()
    cache.get.side_effect = CacheAdapterError("Redis is down")
    store = WrexhamStore(
        cache=cache,
        fixtures_ttl=FIXTURES_TTL,
        live_matches_ttl=LIVE_MATCHES_TTL,
        standings_ttl=STANDINGS_TTL,
    )

    with pytest.raises(CacheAdapterError):
        await store.read_standings()
