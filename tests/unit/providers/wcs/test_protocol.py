# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for merino.providers.wcs.protocol."""

from merino.providers.suggest.sports.backends.sportsdata.common import GameStatus
from merino.providers.wcs.protocol import EventInfo
from tests.wcs.factories import event


def test_event_info_from_event_builds_world_cup_query() -> None:
    """`query` uses the World Cup 2026 prefix and date string."""
    e = event(
        event_id=1,
        day_offset=0,
        hour=14,
        home=("BRA", "Brazil", 90000001),
        away=("ARG", "Argentina", 90000002),
        status=GameStatus.Scheduled,
    )

    info = EventInfo.from_event(e)

    expected_date = e.date.strftime("%d %B %Y")
    assert info.query == f"World Cup 2026 Brazil vs Argentina {expected_date}"


def test_event_info_from_event_uses_source_day_for_world_cup_query() -> None:
    """`query` uses the SportsData source day rather than the UTC kickoff date."""
    e = event(
        event_id=4,
        day_offset=1,
        hour=2,
        home=("IRN", "IR Iran", 90000003),
        away=("NZL", "New Zealand", 90000004),
        status=GameStatus.Scheduled,
        original_date="2026-06-15T00:00:00",
    )

    info = EventInfo.from_event(e)

    assert info.date == "2026-06-16T02:00:00+00:00"
    assert info.query == "World Cup 2026 IR Iran vs New Zealand 15 June 2026"


def test_event_info_from_event_includes_stage() -> None:
    """Ensure stage is propagated from cache to response"""
    e = event(
        event_id=2,
        day_offset=0,
        hour=14,
        home=("BRA", "Brazil", 90000001),
        away=("ARG", "Argentina", 90000002),
        status=GameStatus.Scheduled,
        stage="Round of 32",
    )

    info = EventInfo.from_event(e)
    assert info.stage == "Round of 32"


def test_event_info_from_event_stage_defaults_to_none() -> None:
    """An event with no cached stage serializes stage=None on the widget payload.
    This shouldn't happen with real data.
    """
    e = event(
        event_id=3,
        day_offset=0,
        hour=14,
        home=("BRA", "Brazil", 90000001),
        away=("ARG", "Argentina", 90000002),
        status=GameStatus.Scheduled,
    )

    info = EventInfo.from_event(e)
    assert info.stage is None


def test_event_info_from_event_propagates_group_to_both_teams() -> None:
    e = event(
        event_id=5,
        day_offset=0,
        hour=14,
        home=("BRA", "Brazil", 90000001),
        away=("ARG", "Argentina", 90000002),
        status=GameStatus.Scheduled,
        group="Group A",
    )

    info = EventInfo.from_event(e)

    assert info.home_team.group == "Group A"
    assert info.away_team.group == "Group A"


def test_event_info_from_event_group_defaults_to_none() -> None:
    """Events without a cached group (e.g. knockout matches) emit `None`."""
    e = event(
        event_id=6,
        day_offset=0,
        hour=14,
        home=("BRA", "Brazil", 90000001),
        away=("ARG", "Argentina", 90000002),
        status=GameStatus.Scheduled,
    )

    info = EventInfo.from_event(e)

    assert info.home_team.group is None
    assert info.away_team.group is None
