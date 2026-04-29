# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the WCS matches provider."""

from datetime import date, datetime

from merino.providers.wcs.provider import WcsProvider


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


def test_six_records_two_per_status_type() -> None:
    """The fake set has exactly two past, two live, and two scheduled matches."""
    response = WcsProvider().get_matches(_ANCHOR, limit=None, team_keys=None)

    assert len(response.previous) == 2
    assert len(response.current) == 2
    assert len(response.next_) == 2
    assert all(e.status_type == "past" for e in response.previous)
    assert all(e.status_type == "live" for e in response.current)
    assert all(e.status_type == "scheduled" for e in response.next_)


def test_extra_and_penalty_populated_on_one_finalized_match() -> None:
    """Exactly one finalized match exposes extra-time and penalty-shootout values."""
    response = WcsProvider().get_matches(_ANCHOR, limit=None, team_keys=None)

    finalized_with_extras = [
        e for e in response.previous if e.home_extra is not None and e.home_penalty is not None
    ]
    assert len(finalized_with_extras) == 1
    event = finalized_with_extras[0]
    assert event.away_extra is not None
    assert event.away_penalty is not None


def test_live_extra_time_match_shows_clock_in_extra_play() -> None:
    """A live match in extra time renders its clock in '90+x' form."""
    response = WcsProvider().get_matches(_ANCHOR, limit=None, team_keys=None)

    in_extra = [e for e in response.current if e.period == "ET"]
    assert len(in_extra) == 1
    assert in_extra[0].clock.startswith("90+")
