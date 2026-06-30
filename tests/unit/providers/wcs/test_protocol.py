# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for merino.providers.wcs.protocol."""

from collections.abc import Callable

import pytest
from pytest_mock import MockerFixture

from merino.providers.suggest.sports.backends.sportsdata.common import GameStatus
from merino.providers.suggest.sports.backends.sportsdata.common.wcs_elimination import (
    TBD_TEAM_KEY,
)
from merino.providers.suggest.sports.backends.sportsdata.common.tbd import is_tbd_event_team
from merino.providers.wcs.protocol import EventInfo, TeamInfo
from merino.utils.logos import LogoCategory, LogoManifest
from tests.wcs.factories import event

MakeManifest = Callable[..., LogoManifest]


def test_event_info_from_event_builds_world_cup_query() -> None:
    """`query` uses the World Cup 2026 suffix without game date"""
    e = event(
        event_id=1,
        day_offset=0,
        hour=14,
        home=("BRA", "Brazil", 90000001),
        away=("ARG", "Argentina", 90000002),
        status=GameStatus.Scheduled,
    )

    info = EventInfo.from_event(e)

    assert info.query == "Brazil vs Argentina World Cup 2026"


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
    assert info.query == "IR Iran vs New Zealand World Cup 2026"


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


@pytest.mark.parametrize(
    ("key", "expected_region"),
    [
        pytest.param("CDR", "COD", id="cdr-aliased-to-cod"),
        pytest.param("CVI", "CPV", id="cvi-aliased-to-cpv"),
        pytest.param("BRA", "BRA", id="unlisted-code-unchanged"),
    ],
)
def test_team_info_from_event_team_remaps_region_through_iso_alias(
    key: str, expected_region: str
) -> None:
    """SportsData's wrong ISO3 codes are remapped; unlisted codes pass through."""
    info = TeamInfo.from_event_team({"key": key, "id": 1, "name": "Team"})

    assert info.region == expected_region


def test_team_info_from_event_team_remaps_region_from_country() -> None:
    """An explicit country field is remapped when it is an aliased ISO3 code."""
    info = TeamInfo.from_event_team({"key": "ZZZ", "id": 1, "name": "Team", "country": "CDR"})

    assert info.region == "COD"


@pytest.mark.parametrize(
    ("home", "away", "expected_home_region", "expected_away_region"),
    [
        pytest.param(
            ("CDR", "Congo DR", 90000091),
            ("CVI", "Cape Verde", 90000092),
            "COD",
            "CPV",
            id="both-sides-aliased",
        ),
        pytest.param(
            ("CDR", "Congo DR", 90000091),
            ("BRA", "Brazil", 90000001),
            "COD",
            "BRA",
            id="one-side-aliased",
        ),
    ],
)
def test_event_info_from_event_remaps_team_regions(
    home: tuple[str, str, int],
    away: tuple[str, str, int],
    expected_home_region: str,
    expected_away_region: str,
) -> None:
    """Both home and away regions are remapped through WCS.ISO_alias end-to-end."""
    e = event(
        event_id=30,
        day_offset=0,
        hour=14,
        home=home,
        away=away,
        status=GameStatus.Scheduled,
    )

    info = EventInfo.from_event(e)

    assert info.home_team is not None and info.home_team.region == expected_home_region
    assert info.away_team is not None and info.away_team.region == expected_away_region


def test_is_tbd_event_team_ignores_malformed_placeholder_id() -> None:
    """A malformed placeholder id is not treated as an undecided bracket side."""
    assert is_tbd_event_team({"key": TBD_TEAM_KEY, "id": "bad"}) is False


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
    assert info.query == "Quarterfinals World Cup 2026"


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
    assert info.query == "Quarterfinals World Cup 2026"


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


def test_event_info_from_event_eliminates_knockout_loser_home_wins() -> None:
    """A completed knockout match marks the away (losing) side eliminated."""
    e = event(
        event_id=10,
        day_offset=-1,
        hour=14,
        home=("BRA", "Brazil", 90000001),
        away=("ARG", "Argentina", 90000002),
        status=GameStatus.Final,
        home_score=2,
        away_score=1,
        stage="Round of 16",
        winner="HomeTeam",
    )

    info = EventInfo.from_event(e)

    assert info.home_team is not None and info.home_team.eliminated is False
    assert info.away_team is not None and info.away_team.eliminated is True


def test_event_info_from_event_eliminates_knockout_loser_away_wins() -> None:
    """A completed knockout match marks the home (losing) side eliminated."""
    e = event(
        event_id=11,
        day_offset=-1,
        hour=14,
        home=("BRA", "Brazil", 90000001),
        away=("ARG", "Argentina", 90000002),
        status=GameStatus.Final,
        home_score=0,
        away_score=3,
        stage="Round of 16",
        winner="AwayTeam",
    )

    info = EventInfo.from_event(e)

    assert info.home_team is not None and info.home_team.eliminated is True
    assert info.away_team is not None and info.away_team.eliminated is False


def test_event_info_from_event_group_stage_final_eliminates_neither() -> None:
    """Group Stage standings turn on points, so a single result eliminates no one."""
    e = event(
        event_id=12,
        day_offset=-1,
        hour=14,
        home=("BRA", "Brazil", 90000001),
        away=("ARG", "Argentina", 90000002),
        status=GameStatus.Final,
        home_score=2,
        away_score=1,
        stage="Group Stage",
        winner="HomeTeam",
    )

    info = EventInfo.from_event(e)

    assert info.home_team is not None and info.home_team.eliminated is False
    assert info.away_team is not None and info.away_team.eliminated is False


def test_event_info_from_event_eliminates_loser_after_shootout() -> None:
    """A shootout (F_SO) knockout finish still eliminates the loser."""
    e = event(
        event_id=13,
        day_offset=-1,
        hour=14,
        home=("GER", "Germany", 90000003),
        away=("FRA", "France", 90000004),
        status=GameStatus.F_SO,
        home_score=1,
        away_score=1,
        home_penalty=5,
        away_penalty=4,
        stage="Quarterfinals",
        winner="HomeTeam",
    )

    info = EventInfo.from_event(e)

    assert info.home_team is not None and info.home_team.eliminated is False
    assert info.away_team is not None and info.away_team.eliminated is True


def test_event_info_from_event_in_progress_knockout_eliminates_neither() -> None:
    """A knockout match still in progress eliminates no one."""
    e = event(
        event_id=14,
        day_offset=0,
        hour=14,
        home=("BRA", "Brazil", 90000001),
        away=("ARG", "Argentina", 90000002),
        status=GameStatus.InProgress,
        home_score=1,
        away_score=0,
        stage="Round of 16",
        winner="HomeTeam",
    )

    info = EventInfo.from_event(e)

    assert info.home_team is not None and info.home_team.eliminated is False
    assert info.away_team is not None and info.away_team.eliminated is False


def test_event_info_from_event_final_without_winner_eliminates_neither() -> None:
    """A final knockout match with no declared winner eliminates no one."""
    e = event(
        event_id=15,
        day_offset=-1,
        hour=14,
        home=("BRA", "Brazil", 90000001),
        away=("ARG", "Argentina", 90000002),
        status=GameStatus.Final,
        home_score=1,
        away_score=1,
        stage="Round of 16",
        winner=None,
    )

    info = EventInfo.from_event(e)

    assert info.home_team is not None and info.home_team.eliminated is False
    assert info.away_team is not None and info.away_team.eliminated is False


def test_event_info_from_event_final_without_stage_eliminates_neither() -> None:
    """A final match with no cached stage eliminates no one (missing-stage guard)."""
    e = event(
        event_id=16,
        day_offset=-1,
        hour=14,
        home=("BRA", "Brazil", 90000001),
        away=("ARG", "Argentina", 90000002),
        status=GameStatus.Final,
        home_score=2,
        away_score=1,
        winner="HomeTeam",
    )

    info = EventInfo.from_event(e)

    assert info.home_team is not None and info.home_team.eliminated is False
    assert info.away_team is not None and info.away_team.eliminated is False


def test_event_info_from_event_marks_team_from_eliminated_keys() -> None:
    """A side listed in `eliminated_keys` is eliminated even outside a knockout result."""
    e = event(
        event_id=20,
        day_offset=-1,
        hour=14,
        home=("BRA", "Brazil", 90000001),
        away=("ARG", "Argentina", 90000002),
        status=GameStatus.Final,
        home_score=2,
        away_score=1,
        stage="Group Stage",
        winner="HomeTeam",
    )

    info = EventInfo.from_event(e, eliminated_keys={"ARG"})

    assert info.home_team is not None and info.home_team.eliminated is False
    assert info.away_team is not None and info.away_team.eliminated is True


def test_event_info_from_event_unions_eliminated_keys_with_knockout_loser() -> None:
    """Both the knockout loser and any key-listed side are eliminated together."""
    e = event(
        event_id=21,
        day_offset=-1,
        hour=14,
        home=("BRA", "Brazil", 90000001),
        away=("ARG", "Argentina", 90000002),
        status=GameStatus.Final,
        home_score=2,
        away_score=1,
        stage="Round of 16",
        winner="HomeTeam",
    )

    # The away side loses this knockout match; the home side is independently
    # listed as eliminated by the backend set.
    info = EventInfo.from_event(e, eliminated_keys={"BRA"})

    assert info.home_team is not None and info.home_team.eliminated is True
    assert info.away_team is not None and info.away_team.eliminated is True


def test_event_info_from_event_without_eliminated_keys_preserves_behavior() -> None:
    """Omitting `eliminated_keys` keeps the prior knockout-only behavior."""
    e = event(
        event_id=22,
        day_offset=0,
        hour=14,
        home=("BRA", "Brazil", 90000001),
        away=("ARG", "Argentina", 90000002),
        status=GameStatus.Scheduled,
    )

    info = EventInfo.from_event(e)

    assert info.home_team is not None and info.home_team.eliminated is False
    assert info.away_team is not None and info.away_team.eliminated is False


def test_event_info_from_event_eliminated_keys_skip_tbd_side() -> None:
    """A TBD bracket side stays null even when its placeholder key is not listed."""
    e = event(
        event_id=23,
        day_offset=20,
        hour=20,
        home=("SWE", "Sweden", 90000001),
        away=("TBD", "TBD", 0),
        status=GameStatus.Scheduled,
        original_date="2026-07-05T00:00:00",
        stage="Quarterfinals",
    )

    info = EventInfo.from_event(e, eliminated_keys={"SWE"})

    assert info.home_team is not None and info.home_team.eliminated is True
    assert info.away_team is None


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


@pytest.mark.parametrize(
    ("period", "expected_status"),
    [
        pytest.param("HT", "Break", id="halftime"),
        pytest.param("Regular", "Break", id="regular"),
        pytest.param("1", "Break", id="first-half"),
        pytest.param("2", "Break", id="second-half"),
        pytest.param(None, "Break", id="missing-period"),
        pytest.param("ExtraTime", "In Progress", id="extra-time"),
        pytest.param("Extra Time", "In Progress", id="extra-time-spaced"),
        pytest.param("ET", "In Progress", id="et"),
        pytest.param("ETHT", "In Progress", id="extra-time-halftime"),
        pytest.param("PenaltyShootout", "In Progress", id="penalty-shootout"),
        pytest.param("P", "In Progress", id="penalty-short"),
    ],
)
def test_event_info_from_event_masks_non_halftime_break_status(
    period: str | None, expected_status: str
) -> None:
    """Only regulation halftime is exposed as Break to WCS clients."""
    e = event(
        event_id=17,
        day_offset=0,
        hour=14,
        home=("BRA", "Brazil", 90000001),
        away=("ARG", "Argentina", 90000002),
        status=GameStatus.Break,
        period=period,
    )

    info = EventInfo.from_event(e)

    assert info.status == expected_status
    assert info.status_type == "live"
    assert info.period == period


def test_event_info_from_event_keeps_non_break_extra_time_status() -> None:
    """The extra-time workaround only rewrites Break statuses."""
    e = event(
        event_id=18,
        day_offset=0,
        hour=14,
        home=("BRA", "Brazil", 90000001),
        away=("ARG", "Argentina", 90000002),
        status=GameStatus.InProgress,
        period="ExtraTime",
    )

    info = EventInfo.from_event(e)

    assert info.status == "In Progress"
    assert info.status_type == "live"
    assert info.period == "ExtraTime"


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
