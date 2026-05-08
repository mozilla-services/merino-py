# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the WCS matches provider."""

from datetime import date, datetime
from typing import Any

import pytest

from merino.configs import settings
from merino.exceptions import CacheAdapterError
from merino.providers import wcs as wcs_module
from merino.providers.wcs.provider import WcsProvider
from merino.providers.wcs.protocol import LiveMatchesResponse, TeamInfo, TeamsResponse
from tests.wcs.factories import ANCHOR, build_provider


def test_cache_uses_wcs_redis_settings(mocker) -> None:
    """The WCS API provider reads from the dedicated WCS Redis connection."""
    adapter = object()
    create_redis_clients = mocker.patch.object(
        wcs_module,
        "create_redis_clients",
        return_value=("primary", "replica"),
    )
    redis_adapter = mocker.patch.object(wcs_module, "RedisAdapter", return_value=adapter)

    assert wcs_module._cache() is adapter
    create_redis_clients.assert_called_once_with(
        settings.redis.wcs_server,
        settings.redis.wcs_replica,
        settings.redis.max_connections,
        settings.redis.socket_connect_timeout_sec,
        settings.redis.socket_timeout_sec,
    )
    redis_adapter.assert_called_once_with("primary", "replica")


def _dates(events: list[Any]) -> list[date]:
    return [datetime.fromisoformat(e.date).date() for e in events]


@pytest.mark.asyncio
async def test_buckets_split_by_date() -> None:
    """Each bucket holds events on the correct side of `target_date`."""
    response = await build_provider().get_matches(ANCHOR, limit=None, team_keys=None)

    assert all(d < ANCHOR for d in _dates(response.previous))
    assert all(d == ANCHOR for d in _dates(response.current))
    assert all(d > ANCHOR for d in _dates(response.next_))


@pytest.mark.asyncio
async def test_window_excludes_outside_range() -> None:
    """No event lands more than 7 days from the anchor."""
    response = await build_provider().get_matches(ANCHOR, limit=None, team_keys=None)

    for event in response.previous + response.current + response.next_:
        delta = abs((datetime.fromisoformat(event.date).date() - ANCHOR).days)
        assert delta <= 7


@pytest.mark.asyncio
async def test_buckets_sorted_ascending_by_date() -> None:
    """Each bucket is sorted by event date ascending."""
    response = await build_provider().get_matches(ANCHOR, limit=None, team_keys=None)

    for bucket in (response.previous, response.current, response.next_):
        assert bucket == sorted(bucket, key=lambda e: e.date)


@pytest.mark.asyncio
async def test_limit_keeps_closest_to_target_date() -> None:
    """`previous` keeps the most-recent N, `next` keeps the soonest N."""
    provider = build_provider()
    full = await provider.get_matches(ANCHOR, limit=None, team_keys=None)
    limited = await provider.get_matches(ANCHOR, limit=1, team_keys=None)

    assert len(limited.previous) <= 1
    assert len(limited.current) <= 1
    assert len(limited.next_) <= 1
    if full.previous and limited.previous:
        assert limited.previous[-1].date == full.previous[-1].date
    if full.next_ and limited.next_:
        assert limited.next_[0].date == full.next_[0].date


@pytest.mark.asyncio
async def test_teams_filter_matches_either_side() -> None:
    """Filter retains events where either home or away `key` is in the set."""
    response = await build_provider().get_matches(ANCHOR, limit=None, team_keys=frozenset({"BRA"}))
    events = response.previous + response.current + response.next_

    assert events
    for event in events:
        assert "BRA" in {event.home_team.key, event.away_team.key}


@pytest.mark.asyncio
async def test_response_is_deterministic_for_same_anchor() -> None:
    """Two calls with the same anchor produce identical payloads."""
    provider = build_provider()
    a = await provider.get_matches(ANCHOR, limit=None, team_keys=None)
    b = await provider.get_matches(ANCHOR, limit=None, team_keys=None)

    assert a.model_dump() == b.model_dump()


@pytest.mark.asyncio
async def test_six_records_two_per_status_type() -> None:
    """The stub set has exactly two past, two live, and two scheduled matches."""
    response = await build_provider().get_matches(ANCHOR, limit=None, team_keys=None)

    assert len(response.previous) == 2
    assert len(response.current) == 2
    assert len(response.next_) == 2
    assert all(e.status_type == "past" for e in response.previous)
    assert all(e.status_type == "live" for e in response.current)
    assert all(e.status_type == "scheduled" for e in response.next_)


@pytest.mark.asyncio
async def test_public_sport_identifier_is_soccer() -> None:
    """WCS responses expose the stable widget sport value, not the internal league key."""
    response = await build_provider().get_matches(ANCHOR, limit=None, team_keys=None)
    events = response.previous + response.current + response.next_

    assert events
    assert {event.sport for event in events} == {"soccer"}


@pytest.mark.asyncio
async def test_extra_and_penalty_populated_on_one_finalized_match() -> None:
    """Exactly one finalized match exposes extra-time and penalty-shootout values."""
    response = await build_provider().get_matches(ANCHOR, limit=None, team_keys=None)

    finalized_with_extras = [
        e for e in response.previous if e.home_extra is not None and e.home_penalty is not None
    ]
    assert len(finalized_with_extras) == 1
    event = finalized_with_extras[0]
    assert event.away_extra is not None
    assert event.away_penalty is not None


@pytest.mark.asyncio
async def test_live_extra_time_match_shows_clock_in_extra_play() -> None:
    """A live match in extra time renders its clock in '90+x' form."""
    response = await build_provider().get_matches(ANCHOR, limit=None, team_keys=None)

    in_extra = [e for e in response.current if e.period == "ET"]
    assert len(in_extra) == 1
    assert in_extra[0].clock.startswith("90+")


@pytest.mark.asyncio
async def test_live_returns_only_in_progress_events() -> None:
    """`get_live_matches` returns the two fake live events."""
    response = await build_provider(events=[]).get_live_matches(team_keys=None)

    assert len(response.matches) == 2
    assert all(e.status_type == "live" for e in response.matches)


@pytest.mark.asyncio
async def test_live_matches_sorted_ascending_by_date() -> None:
    """Live events are sorted ascending by `date`."""
    matches: LiveMatchesResponse = await build_provider().get_live_matches(team_keys=None)
    assert matches.matches == sorted(matches.matches, key=lambda e: e.date)


@pytest.mark.asyncio
async def test_live_teams_filter_matches_either_side() -> None:
    """Filter retains live events where either side plays for the listed team."""
    response = await build_provider().get_live_matches(team_keys=frozenset({"BRA"}))

    assert response.matches
    for event in response.matches:
        assert "BRA" in {event.home_team.key, event.away_team.key}


@pytest.mark.asyncio
async def test_live_unknown_team_returns_empty() -> None:
    """No match for the filter yields an empty list, not an error."""
    response = await build_provider().get_live_matches(team_keys=frozenset({"ZZZ"}))
    assert response.matches == []


@pytest.mark.asyncio
async def test_live_is_deterministic_within_same_utc_day() -> None:
    """Two calls in the same UTC day produce identical payloads."""
    provider = build_provider(events=[])
    a = await provider.get_live_matches(team_keys=None)
    b = await provider.get_live_matches(team_keys=None)
    assert a.model_dump() == b.model_dump()


@pytest.mark.asyncio
async def test_get_teams_count() -> None:
    """The static tournament roster has exactly 48 teams, all TeamInfo instances."""
    response = build_provider().get_teams()
    assert len(response.teams) == 48
    assert isinstance(response, TeamsResponse)
    assert all(isinstance(team, TeamInfo) for team in response.teams)


@pytest.mark.asyncio
async def test_empty_cache_returns_empty_payloads() -> None:
    """An empty WCS event cache returns empty matches while live/teams stay static."""
    provider = build_provider(events=[])

    matches = await provider.get_matches(ANCHOR, limit=None, team_keys=None)
    assert matches.model_dump(by_alias=True) == {
        "previous": [],
        "current": [],
        "next": [],
    }
    assert len((await provider.get_live_matches(team_keys=None)).matches) == 2
    assert len(provider.get_teams().teams) == 48


@pytest.mark.asyncio
async def test_cache_error_returns_empty_payloads(mocker) -> None:
    """A transient WCS cache read failure returns empty cache-backed envelopes."""
    sport = mocker.Mock()
    sport.get_events_by_date = mocker.AsyncMock(side_effect=CacheAdapterError("redis down"))
    metrics_client = mocker.Mock()
    provider = WcsProvider(sport=sport, metrics_client=metrics_client)

    matches = await provider.get_matches(ANCHOR, limit=None, team_keys=None)
    assert matches.model_dump(by_alias=True) == {
        "previous": [],
        "current": [],
        "next": [],
    }
    assert len((await provider.get_live_matches(team_keys=None)).matches) == 2
    assert len(provider.get_teams().teams) == 48
    metrics_client.increment.assert_any_call("wcs.cache_error", tags={"endpoint": "matches"})
