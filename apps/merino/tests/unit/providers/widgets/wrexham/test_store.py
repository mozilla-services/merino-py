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

from merino.exceptions import CacheAdapterError
from merino.providers.widgets.wrexham.protocol import MatchStatus
from merino.providers.widgets.wrexham.store import (
    LIVE_MATCHES_KEY,
    STANDINGS_KEY,
    WrexhamStore,
    fixtures_key,
)
from tests.types import FilterCaplogFixture
from tests.unit.providers.widgets.wrexham.conftest import FakeCache, MakeMatch, MakeStanding

NOW = datetime(2026, 11, 2, 15, 30, tzinfo=UTC)
CHAMPIONSHIP_ID = 34
FA_CUP_ID = 27


def test_key_names_use_the_versioned_prefix() -> None:
    """Every key uses the `wrexham:v1:` prefix, with one fixtures key per competition."""
    assert fixtures_key(34) == "wrexham:v1:fixtures:34"
    assert fixtures_key(27) == "wrexham:v1:fixtures:27"
    assert LIVE_MATCHES_KEY == "wrexham:v1:live"
    assert STANDINGS_KEY == "wrexham:v1:standings"


@freeze_time(NOW)
@pytest.mark.asyncio
async def test_fixtures_round_trip_per_competition(
    store: WrexhamStore, fake_cache: FakeCache, make_match: MakeMatch
) -> None:
    """Fixtures are written and read per competition, with the fetch time and expiry."""
    championship = [make_match(1), make_match(2)]
    fa_cup = [make_match(3, competition_id=FA_CUP_ID)]

    await store.write_fixtures(CHAMPIONSHIP_ID, championship)
    await store.write_fixtures(FA_CUP_ID, fa_cup)

    assert await store.read_fixtures(CHAMPIONSHIP_ID) == (championship, NOW)
    assert await store.read_fixtures(FA_CUP_ID) == (fa_cup, NOW)
    assert fake_cache.ttls[fixtures_key(CHAMPIONSHIP_ID)] == store.fixtures_ttl


@freeze_time(NOW)
@pytest.mark.asyncio
async def test_live_matches_round_trip(
    store: WrexhamStore, fake_cache: FakeCache, make_match: MakeMatch
) -> None:
    """Live matches are written and read under one key, with the fetch time and expiry."""
    live = [make_match(4, status=MatchStatus.InProgress)]

    await store.write_live_matches(live)

    assert await store.read_live_matches() == (live, NOW)
    assert fake_cache.ttls[LIVE_MATCHES_KEY] == store.live_matches_ttl


@freeze_time(NOW)
@pytest.mark.asyncio
async def test_empty_live_matches_round_trip(store: WrexhamStore) -> None:
    """An empty list of live matches is stored as empty, not as missing data."""
    await store.write_live_matches([])

    assert await store.read_live_matches() == ([], NOW)


@freeze_time(NOW)
@pytest.mark.asyncio
async def test_standings_round_trip(
    store: WrexhamStore, fake_cache: FakeCache, make_standing: MakeStanding
) -> None:
    """The table is written and read with its fetch time and expiry."""
    standings = [make_standing(1), make_standing(2), make_standing(3)]

    await store.write_standings(standings)

    assert await store.read_standings() == (standings, NOW)
    assert fake_cache.ttls[STANDINGS_KEY] == store.standings_ttl


@freeze_time(NOW)
@pytest.mark.asyncio
async def test_written_value_holds_the_fetch_time_and_data(
    store: WrexhamStore, fake_cache: FakeCache
) -> None:
    """The stored JSON holds the fetch time next to the data."""
    await store.write_live_matches([])

    assert orjson.loads(fake_cache.values[LIVE_MATCHES_KEY]) == {
        "fetched_at": "2026-11-02T15:30:00Z",
        "data": [],
    }


@pytest.mark.asyncio
async def test_read_accepts_a_utc_offset_written_as_plus_zero(
    store: WrexhamStore, fake_cache: FakeCache
) -> None:
    """A fetch time written as `+00:00` instead of `Z` is still read correctly."""
    fake_cache.values[LIVE_MATCHES_KEY] = (
        b'{"fetched_at": "2026-11-02T15:30:00+00:00", "data": []}'
    )

    assert await store.read_live_matches() == ([], NOW)


@pytest.mark.parametrize("field", ["kickoff", "updated_at"])
@pytest.mark.asyncio
async def test_read_returns_none_when_a_match_time_has_no_timezone(
    store: WrexhamStore, fake_cache: FakeCache, make_match: MakeMatch, field: str
) -> None:
    """A stored match whose time has no timezone is treated as missing."""
    await store.write_live_matches([make_match(1)])
    stored = orjson.loads(fake_cache.values[LIVE_MATCHES_KEY])
    stored["data"][0][field] = "2026-10-31T15:00:00"
    fake_cache.values[LIVE_MATCHES_KEY] = orjson.dumps(stored)

    assert await store.read_live_matches() is None


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
    fake_cache: FakeCache,
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
    raw: bytes,
) -> None:
    """A stored value that can't be parsed is logged and treated as missing."""
    fake_cache.values[STANDINGS_KEY] = raw

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
        fixtures_ttl=timedelta(hours=3),
        live_matches_ttl=timedelta(minutes=10),
        standings_ttl=timedelta(hours=6),
    )

    with pytest.raises(CacheAdapterError):
        await store.read_standings()
