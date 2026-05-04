# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the WCS matches provider."""

from datetime import date, datetime

from merino.providers.wcs.provider import WcsProvider

# Inside the tournament window (June 11 – July 2026); the ±7-day slice
# around this anchor has 11 previous, 4 current, and 27 next events.
_ANCHOR = date(2026, 6, 15)


def _dates(events) -> list[date]:
    return [datetime.fromisoformat(e.date).date() for e in events]


def test_buckets_split_by_date() -> None:
    """Each bucket holds events on the correct side of `target_date`."""
    response = WcsProvider().get_matches(_ANCHOR, limit=None, team_keys=None)

    assert all(d < _ANCHOR for d in _dates(response.previous))
    assert all(d == _ANCHOR for d in _dates(response.current))
    assert all(d > _ANCHOR for d in _dates(response.next_))


def test_window_excludes_outside_range() -> None:
    """No event lands more than 7 days from the anchor."""
    response = WcsProvider().get_matches(_ANCHOR, limit=None, team_keys=None)

    for event in response.previous + response.current + response.next_:
        delta = abs((datetime.fromisoformat(event.date).date() - _ANCHOR).days)
        assert delta <= 7


def test_buckets_sorted_ascending_by_date() -> None:
    """Each bucket is sorted by event date ascending."""
    response = WcsProvider().get_matches(_ANCHOR, limit=None, team_keys=None)

    for bucket in (response.previous, response.current, response.next_):
        assert bucket == sorted(bucket, key=lambda e: e.date)


def test_limit_keeps_closest_to_target_date() -> None:
    """`previous` keeps the most-recent N, `next` keeps the soonest N."""
    full = WcsProvider().get_matches(_ANCHOR, limit=None, team_keys=None)
    limited = WcsProvider().get_matches(_ANCHOR, limit=1, team_keys=None)

    assert len(limited.previous) <= 1
    assert len(limited.current) <= 1
    assert len(limited.next_) <= 1
    if full.previous and limited.previous:
        assert limited.previous[-1].date == full.previous[-1].date
    if full.next_ and limited.next_:
        assert limited.next_[0].date == full.next_[0].date


def test_teams_filter_matches_either_side() -> None:
    """Filter retains events where either home or away `key` is in the set."""
    response = WcsProvider().get_matches(_ANCHOR, limit=None, team_keys=frozenset({"BRA"}))
    events = response.previous + response.current + response.next_

    assert events
    for event in events:
        assert "BRA" in {event.home_team.key, event.away_team.key}


def test_response_is_deterministic_for_same_anchor() -> None:
    """Two calls with the same anchor produce identical payloads."""
    a = WcsProvider().get_matches(_ANCHOR, limit=None, team_keys=None)
    b = WcsProvider().get_matches(_ANCHOR, limit=None, team_keys=None)

    assert a.model_dump() == b.model_dump()


def test_buckets_populated_for_anchor_in_tournament() -> None:
    """An anchor inside the tournament window returns events in every bucket."""
    response = WcsProvider().get_matches(_ANCHOR, limit=None, team_keys=None)

    assert response.previous
    assert response.current
    assert response.next_


def test_live_returns_only_in_progress_events() -> None:
    """`get_live_matches` never returns events with a non-live status_type."""
    response = WcsProvider().get_live_matches(team_keys=None)

    assert all(e.status_type == "live" for e in response.matches)


def test_live_matches_sorted_ascending_by_date() -> None:
    """Live events are sorted ascending by `date`."""
    matches = WcsProvider().get_live_matches(team_keys=None).matches
    assert matches == sorted(matches, key=lambda e: e.date)


def test_live_teams_filter_matches_either_side() -> None:
    """Filter retains live events where either side plays for the listed team."""
    response = WcsProvider().get_live_matches(team_keys=frozenset({"BRA"}))

    assert response.matches
    for event in response.matches:
        assert "BRA" in {event.home_team.key, event.away_team.key}


def test_live_unknown_team_returns_empty() -> None:
    """No match for the filter yields an empty list, not an error."""
    response = WcsProvider().get_live_matches(team_keys=frozenset({"ZZZ"}))
    assert response.matches == []


def test_live_is_deterministic_within_same_utc_day() -> None:
    """Two calls in the same UTC day produce identical payloads."""
    a = WcsProvider().get_live_matches(team_keys=None)
    b = WcsProvider().get_live_matches(team_keys=None)
    assert a.model_dump() == b.model_dump()


def test_event_info_contract() -> None:
    """Every EventInfo exposes required typed fields."""
    response = WcsProvider().get_matches(_ANCHOR, limit=1, team_keys=None)
    events = response.previous + response.current + response.next_

    assert events
    for event in events:
        datetime.fromisoformat(event.date)  # parseable ISO datetime with tz
        assert isinstance(event.global_event_id, int)
        assert isinstance(event.status, str)
        assert event.status_type in ("past", "live", "scheduled")
        assert isinstance(event.clock, str)
        assert isinstance(event.updated, int)
        assert event.sport == "soccer"


def test_team_info_contract() -> None:
    """TeamInfo fields are present and correctly typed on every event."""
    response = WcsProvider().get_matches(_ANCHOR, limit=1, team_keys=None)
    events = response.previous + response.current + response.next_

    assert events
    for event in events:
        for team in (event.home_team, event.away_team):
            assert len(team.key) == 3
            assert isinstance(team.global_team_id, int)
            assert isinstance(team.name, str)
            assert isinstance(team.eliminated, bool)
            assert set(team.standing.keys()) >= {"wins", "losses", "draws", "points"}
