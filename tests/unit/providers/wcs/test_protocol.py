# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for merino.providers.wcs.protocol."""

from collections.abc import Callable

from pytest_mock import MockerFixture

from merino.providers.suggest.sports.backends.sportsdata.common import GameStatus
from merino.providers.suggest.sports.backends.sportsdata.common.wcs_elimination import (
    TBD_TEAM_KEY,
)
from merino.providers.wcs.protocol import EventInfo, TeamInfo, _is_tbd_event_team
from merino.utils.logos import LogoCategory, LogoManifest
from tests.wcs.factories import event

MakeManifest = Callable[..., LogoManifest]


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


def test_team_info_icon_url_can_be_none_when_logo_is_missing(
    mocker: MockerFixture,
    make_manifest: MakeManifest,
) -> None:
    """Teams without a manifest logo serialize icon_url=None."""
    mocker.patch("merino.providers.wcs.protocol.load_manifest", return_value=make_manifest())

    info = TeamInfo.from_event_team({"key": "ZZZ", "id": 1, "name": "Unknown"})

    assert info.icon_url is None


def test_team_info_icon_url_uses_png_when_svg_is_missing(
    mocker: MockerFixture,
    make_manifest: MakeManifest,
) -> None:
    """Manifest entries without SVGs fall back to their PNG URL."""
    mocker.patch(
        "merino.providers.wcs.protocol.load_manifest",
        return_value=make_manifest((LogoCategory.Nations, "ZZZ")),
    )

    info = TeamInfo.from_event_team({"key": "ZZZ", "id": 1, "name": "Unknown"})

    assert str(info.icon_url).endswith("/logos/nations/nations_zzz.png")


def test_is_tbd_event_team_ignores_malformed_placeholder_id() -> None:
    """A malformed placeholder id is not treated as an undecided bracket side."""
    assert _is_tbd_event_team({"key": TBD_TEAM_KEY, "id": "bad"}) is False


def test_event_info_from_event_builds_tbd_world_cup_query() -> None:
    """Placeholder cache teams serialize as null while preserving the click query."""
    e = event(
        event_id=5,
        day_offset=20,
        hour=20,
        home=("TBD", "TBD", 0),
        away=("TBD", "TBD", 0),
        status=GameStatus.Scheduled,
        original_date="2026-07-05T00:00:00",
        stage="Quarterfinals",
    )

    info = EventInfo.from_event(e)

    assert info.home_team is None
    assert info.away_team is None
    assert info.query == "World Cup 2026 TBD vs TBD 05 July 2026"


def test_event_info_from_event_serializes_one_tbd_side_as_null() -> None:
    """A partially known bracket match keeps the real side and nulls the TBD side."""
    e = event(
        event_id=8,
        day_offset=20,
        hour=20,
        home=("SWE", "Sweden", 90000001),
        away=("TBD", "TBD", 0),
        status=GameStatus.Scheduled,
        original_date="2026-07-05T00:00:00",
        stage="Quarterfinals",
    )

    info = EventInfo.from_event(e)

    assert info.home_team is not None
    assert info.home_team.name == "Sweden"
    assert info.away_team is None
    assert info.query == "World Cup 2026 Sweden vs TBD 05 July 2026"


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


def test_event_info_from_event_stage_defaults_to_empty_string() -> None:
    """An event with no cached stage serializes a non-null stage value.
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
    assert info.stage == ""


def test_event_info_from_event_missing_period_and_clock_stay_null() -> None:
    """Scheduled matches without period or clock metadata serialize nulls."""
    e = event(
        event_id=7,
        day_offset=0,
        hour=14,
        home=("BRA", "Brazil", 90000001),
        away=("ARG", "Argentina", 90000002),
        status=GameStatus.Scheduled,
    )

    info = EventInfo.from_event(e)

    assert info.period is None
    assert info.clock is None


def test_event_info_from_event_propagates_group_to_both_teams() -> None:
    """The event-level group surfaces on both team info entries."""
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

    assert info.home_team is not None
    assert info.away_team is not None
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

    assert info.home_team is not None
    assert info.away_team is not None
    assert info.home_team.group is None
    assert info.away_team.group is None
