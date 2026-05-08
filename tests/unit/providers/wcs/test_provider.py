# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the WCS matches provider."""

from datetime import date, datetime
import pytest

from merino.configs import settings
from merino.providers.wcs.protocol import TeamsResponse
from merino.providers.wcs.protocol import TeamInfo
from merino.providers.wcs.provider import WcsProvider


_ANCHOR = datetime(2026, 6, 15)

# These tests were machine generated and need to be replaced with ones that
# actually test the interface.

def _dates(events) -> list[date]:
    return [datetime.fromisoformat(e.date).date() for e in events]


@pytest.mark.asyncio
async def test_buckets_split_by_date() -> None:
    """Each bucket holds events on the correct side of `target_date`."""
    response = await WcsProvider(settings=settings.providers.sports).get_matches(
        _ANCHOR, limit=None, team_keys=None
    )

    assert all(d < _ANCHOR for d in _dates(response.previous))
    assert all(d == _ANCHOR for d in _dates(response.current))
    assert all(d > _ANCHOR for d in _dates(response.next_))


@pytest.mark.asyncio
async def test_window_excludes_outside_range() -> None:
    """No event lands more than 7 days from the anchor."""
    response = await WcsProvider(settings=settings.providers.sports).get_matches(
        _ANCHOR, limit=None, team_keys=None
    )

    for event in response.previous + response.current + response.next_:
        delta: int = abs((datetime.fromisoformat(event.date).date() - _ANCHOR).days)
        assert delta <= 7


@pytest.mark.asyncio
async def test_buckets_sorted_ascending_by_date() -> None:
    """Each bucket is sorted by event date ascending."""
    response = await WcsProvider(settings=settings.providers.sports).get_matches(
        _ANCHOR, limit=None, team_keys=None
    )

    for bucket in (response.previous, response.current, response.next_):
        assert bucket == sorted(bucket, key=lambda e: e.date)


@pytest.mark.asyncio
async def test_limit_keeps_closest_to_target_date() -> None:
    """`previous` keeps the most-recent N, `next` keeps the soonest N."""
    sport = WcsProvider(settings=settings.providers.sports)
    full = await sport.get_matches(_ANCHOR, limit=None, team_keys=None)
    limited = await sport.get_matches(_ANCHOR, limit=1, team_keys=None)

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
    response = await WcsProvider(settings=settings.providers.sports).get_matches(
        _ANCHOR, limit=None, team_keys=frozenset({"BRA"})
    )
    events = response.previous + response.current + response.next_

    assert events
    for event in events:
        assert "BRA" in {event.home_team.key, event.away_team.key}


@pytest.mark.asyncio
async def test_response_is_deterministic_for_same_anchor() -> None:
    """Two calls with the same anchor produce identical payloads."""
    sport = WcsProvider(settings=settings.providers.sports)
    a = await sport.get_matches(_ANCHOR, limit=None, team_keys=None)
    b = await sport.get_matches(_ANCHOR, limit=None, team_keys=None)

    assert a.model_dump() == b.model_dump()


@pytest.mark.asyncio
async def test_six_records_two_per_status_type() -> None:
    """The fake set has exactly two past, two live, and two scheduled matches."""
    response = await WcsProvider(settings=settings.providers.sports).get_matches(
        _ANCHOR, limit=None, team_keys=None
    )

    assert len(response.previous) == 2
    assert len(response.current) == 2
    assert len(response.next_) == 2
    assert all(e.status_type == "past" for e in response.previous)
    assert all(e.status_type == "live" for e in response.current)
    assert all(e.status_type == "scheduled" for e in response.next_)


@pytest.mark.asyncio
async def test_extra_and_penalty_populated_on_one_finalized_match() -> None:
    """Exactly one finalized match exposes extra-time and penalty-shootout values."""
    response = await WcsProvider(settings=settings.providers.sports).get_matches(
        _ANCHOR, limit=None, team_keys=None
    )

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
    response = await WcsProvider(settings=settings.providers.sports).get_matches(
        _ANCHOR, limit=None, team_keys=None
    )

    in_extra = [e for e in response.current if e.period == "ET"]
    assert len(in_extra) == 1
    assert in_extra[0].clock.startswith("90+")


@pytest.mark.asyncio
async def test_live_returns_only_in_progress_events() -> None:
    """`get_live_matches` returns the two `live` events from the fake set."""
    response = await WcsProvider(settings=settings.providers.sports).get_live_matches(
        team_keys=None
    )

    assert len(response.matches) == 2
    assert all(e.status_type == "live" for e in response.matches)


# @pytest.mark.asyncio
# async def test_live_matches_sorted_ascending_by_date() -> None:
#     """Live events are sorted ascending by `date`."""
#     matches = await WcsProvider(settings=settings.providers.sports).get_live_matches(
#         team_keys=None
#     )
#     assert matches == sorted(matches, key=lambda e: e.date)


@pytest.mark.asyncio
async def test_live_teams_filter_matches_either_side() -> None:
    """Filter retains live events where either side plays for the listed team."""
    response = await WcsProvider(settings=settings.providers.sports).get_live_matches(
        team_keys=frozenset({"BRA"})
    )

    assert response.matches
    for event in response.matches:
        assert "BRA" in {event.home_team.key, event.away_team.key}


@pytest.mark.asyncio
async def test_live_unknown_team_returns_empty() -> None:
    """No match for the filter yields an empty list, not an error."""
    response = await WcsProvider(settings=settings.providers.sports).get_live_matches(
        team_keys=frozenset({"ZZZ"})
    )
    assert response.matches == []


@pytest.mark.asyncio
async def test_live_is_deterministic_within_same_utc_day() -> None:
    """Two calls in the same UTC day produce identical payloads."""
    sport = WcsProvider(settings=settings.providers.sports)
    a = await sport.get_live_matches(team_keys=None)
    b = await sport.get_live_matches(team_keys=None)
    assert a.model_dump() == b.model_dump()


@pytest.mark.asyncio
async def test_get_teams_count() -> None:
    """The full tournament roster has exactly 48 teams (12 groups × 4), all TeamInfo instances."""
    # TODO: preload the Redis cash, (or pretend that we did)
    response = await WcsProvider(settings=settings.providers.sports).get_teams()
    assert len(response.teams) == 48
    assert isinstance(response, TeamsResponse)
    assert all(isinstance(team, TeamInfo) for team in response.teams)
