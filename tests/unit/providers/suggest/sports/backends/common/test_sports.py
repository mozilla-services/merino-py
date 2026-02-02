"""Unit Tests for Sports."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, cast

import freezegun
import pytest
from httpx import AsyncClient
from pytest_mock import MockerFixture

from merino.configs import settings
from merino.providers.suggest.sports.backends.sportsdata.common.data import Sport, Team
from merino.providers.suggest.sports.backends.sportsdata.common.error import (
    SportsDataError,
    SportsDataWarning,
)
from merino.providers.suggest.sports.backends.sportsdata.common import GameStatus
from merino.providers.suggest.sports.backends.sportsdata.common.sports import (
    NFL,
    NHL,
    NBA,
    UCL,
)


@pytest.fixture
def mock_client(mocker: MockerFixture) -> AsyncClient:
    """Mock Async Client."""
    return cast(AsyncClient, mocker.Mock(spec=AsyncClient))


@pytest.fixture
def nfl_teams_payload() -> list[dict]:
    """NFL team payload."""
    return [
        {
            "Key": "PIT",
            "Name": "Steelers",
            "City": "Pittsburgh",
            "AreaName": "PA",
            "FullName": "Pittsburgh Steelers",
            "Nickname1": "Steelers",
            "GlobalTeamId": 28,
            "PrimaryColor": "000000",
            "SecondaryColor": "FFB612",
        },
        {
            "Key": "MIN",
            "Name": "Vikings",
            "City": "Minneapolis",
            "AreaName": "MN",
            "GlobalTeamId": 20,
            "FullName": "Minnesota Vikings",
            "PrimaryColor": "4F2683",
            "SecondaryColor": "FFC62F",
        },
    ]


@pytest.fixture
def nhl_nba_teams_payload() -> list[dict]:
    """NHL/NBA team payload."""
    return [
        {
            "Key": "VAN",
            "Name": "Canucks",
            "City": "Vancouver",
            "AreaName": "",
            "FullName": "Vancouver Canucks",
            "GlobalTeamId": 30000024,
            "PrimaryColor": "00205B",
            "SecondaryColor": "00843d",
        },
        {
            "Key": "TOR",
            "Name": "Maple Leafs",
            "City": "Toronto",
            "AreaName": "",
            "FullName": "Toronto Maple Leafs",
            "GlobalTeamID": 30000007,
            "PrimaryColor": "00205B",
            "SecondaryColor": "None",
        },
    ]


@pytest.fixture
def weird_schedules_payload() -> list[dict]:
    """Schedules payload that are out and in window."""
    return [
        {
            "GameId": 23869,
            "Season": 2026,
            "SeasonType": 2,
            "Status": "Final",
            "Day": "2025-09-21T00:00:00",
            "DateTime": "2025-09-21T21:30:00",
            "Updated": "2025-09-29T04:10:57",
            "IsClosed": True,
            "AwayTeam": "AFC",
            "HomeTeam": "TOR",
            "StadiumID": 9,
            "AwayTeamScore": 2,
            "HomeTeamScore": 3,
            "GlobalGameID": 30023869,
            "GlobalAwayTeamID": 30000041,
            "GlobalHomeTeamID": 30000019,
            "GameEndDateTime": "2025-09-22T00:10:17",
            "NeutralVenue": False,
            "DateTimeUTC": "2025-09-22T01:30:00",
            "AwayTeamID": 41,
            "HomeTeamID": 19,
            "SeriesInfo": None,
        }
    ]


@pytest.fixture
def schedules_payload() -> list[dict]:
    """Schedules payload that are out and in window."""
    return [
        {
            "GameId": 23869,
            "Season": 2026,
            "SeasonType": 2,
            "Status": "Final",
            "Day": "2025-09-21T00:00:00",
            "DateTime": "2025-09-21T21:30:00",
            "Updated": "2025-09-29T04:10:57",
            "IsClosed": True,
            "AwayTeam": "VAN",
            "HomeTeam": "TOR",
            "StadiumID": 9,
            "AwayTeamScore": 2,
            "HomeTeamScore": 3,
            "GlobalGameID": 30023869,
            "GlobalAwayTeamID": 30000024,
            "GlobalHomeTeamID": 30000007,
            "GameEndDateTime": "2025-09-22T00:10:17",
            "NeutralVenue": False,
            "DateTimeUTC": "2025-09-22T01:30:00",
            "AwayTeamID": 41,
            "HomeTeamID": 19,
            "SeriesInfo": None,
        },
        {
            "GameId": 22222,
            "Season": 2000,
            "SeasonType": 2,
            "Status": "Final",
            "Day": "2000-01-01T00:00:00",
            "DateTime": "2000-01-01T21:30:00",
            "Updated": "2000-01-01T04:10:57",
            "IsClosed": True,
            "AwayTeam": "VAN",
            "HomeTeam": "TOR",
            "StadiumID": 9,
            "AwayTeamScore": 0,
            "HomeTeamScore": 0,
            "GlobalGameID": 0,
            "GlobalAwayTeamID": 30000024,
            "GlobalHomeTeamID": 30000007,
            "GameEndDateTime": "2000-09-22T00:10:17",
            "NeutralVenue": False,
            "DateTimeUTC": "2000-09-22T01:30:00",
            "AwayTeamID": 41,
            "HomeTeamID": 19,
            "SeriesInfo": None,
        },
    ]


@pytest.fixture
def nfl_scores_payload() -> list[dict[str, Any]]:
    """NFL scores payload."""
    base = {
        "Quarter": None,
        "TimeRemaining": None,
        "QuarterDescription": "",
        "GameEndDateTime": None,
        "AwayScore": None,
        "HomeScore": None,
        "GameID": 19047,
        "GlobalGameID": 19047,
        "ScoreID": 19047,
        "GameKey": "202510428",
        "Season": 2025,
        "SeasonType": 1,
        "Status": "Scheduled",
        "Canceled": False,
        "AwayTeam": "MIN",
        "HomeTeam": "PIT",
        "GlobalAwayTeamID": 20,
        "GlobalHomeTeamID": 28,
        "AwayTeamID": 20,
        "HomeTeamID": 28,
        "StadiumID": 90,
        "Closed": False,
        "IsClosed": False,
        "Week": 4,
    }
    within = "2025-09-22T13:30:00"  # UTC
    outside = "2026-01-22T13:30:00"
    return [
        {
            **base,
            "Date": "2025-09-22T09:30:00",
            "Day": "2025-09-22T00:00:00",
            "DateTime": "2025-09-22T09:30:00",
            "DateTimeUTC": within,
            "LastUpdated": "2025-09-21T12:00:00",
        },
        {
            **base,
            "GlobalGameID": 22222,
            "GameID": 22222,
            "ScoreID": 22222,
            "Date": "2026-01-22T09:30:00",
            "Day": "2026-01-22T00:00:00",
            "DateTime": "2026-01-22T09:30:00",
            "DateTimeUTC": outside,
            "LastUpdated": "2026-01-21T12:00:00",
        },
    ]


def _mk_team(key: str, name: str, locale: str, id: int) -> Team:
    """Team function."""
    return Team(
        fullname=name,
        terms=name.lower(),
        name=name,
        id=id,
        key=key,
        locale=locale,
        aliases=[name],
        colors=["000000"],
        updated=datetime(2025, 9, 22, tzinfo=timezone.utc),
        expiry=datetime(2026, 9, 22, tzinfo=timezone.utc),
    )


@pytest.mark.parametrize("cls", [NFL, NHL, NBA, UCL], ids=["NFL", "NHL", "NBA", "UCL"])
@pytest.mark.asyncio
async def test_get_team_lookup(cls: type[Sport]) -> None:
    """Test team lookups."""
    sport: Sport = cls(settings=settings.providers.sports, base_url="", name="")

    t = _mk_team("PIT", "Pittsburgh Steelers", "Pittsburgh PA", 28)

    sport.teams = {28: t}
    assert await sport.get_team(0) is None

    sport.teams = {28: t}
    found = await sport.get_team(28)
    assert isinstance(found, Team) and found.name == "Pittsburgh Steelers"


@pytest.mark.asyncio
@freezegun.freeze_time("2025-09-22T00:00:00", tz_offset=0)
async def test_nfl_update_teams(
    nfl_teams_payload: list[dict], mock_client: AsyncClient, mocker: MockerFixture
) -> None:
    """Test NFL team updates."""
    nfl = NFL(settings=settings.providers.sports)
    timeframe = [
        {
            "SeasonType": 1,
            "Season": 2025,
            "Week": 3,
            "Name": "Week 3",
            "ApiSeason": "2025REG",
            "ApiWeek": "3",
            "StartDate": "2025-09-17T00:00:00",
            "EndDate": "2025-09-23T23:59:59",
        }
    ]
    get_data = mocker.patch(
        "merino.providers.suggest.sports.backends.sportsdata.common.sports.get_data",
        side_effect=[timeframe, nfl_teams_payload],
    )

    await nfl.update_teams(client=mock_client)

    assert nfl.season == "2025REG"
    assert nfl.week == "3"
    assert set(nfl.teams.keys()) == {28, 20}
    pit = nfl.teams[28]
    assert pit.name == "Steelers"
    assert get_data.call_count == 2
    assert "/Timeframes/current" in get_data.call_args_list[0].kwargs["url"]
    assert "/Teams?key=" in get_data.call_args_list[1].kwargs["url"]


@pytest.mark.asyncio
@freezegun.freeze_time("2025-09-22T00:00:00", tz_offset=0)
async def test_nfl_superbowl(
    nfl_teams_payload: list[dict], mock_client: AsyncClient, mocker: MockerFixture
) -> None:
    """Test NFL override for the Superbowl vs. Pro Bowl."""
    nfl = NFL(settings=settings.providers.sports)
    timeframe = [
        {
            "SeasonType": 5,
            "Season": 2025,
            "Week": 1,
            "Name": "Pro Bowl",
            "ApiSeason": "2025STAR",
            "ApiWeek": "1",
            "StartDate": "2025-09-17T00:00:00",
            "EndDate": "2025-09-23T23:59:59",
        }
    ]
    mocker.patch(
        "merino.providers.suggest.sports.backends.sportsdata.common.sports.get_data",
        side_effect=[timeframe, nfl_teams_payload],
    )

    await nfl.get_season(client=mock_client)

    assert nfl.season == "2025POST"
    assert nfl.week == 4


@pytest.mark.asyncio
async def test_nhl_update_teams_with_none_season(
    mocker: MockerFixture, mock_client: AsyncClient
) -> None:
    """Test NHL team updates with None season."""
    nhl = NHL(settings=settings.providers.sports)
    get_data = mocker.patch(
        "merino.providers.suggest.sports.backends.sportsdata.common.sports.get_data",
        return_value={"ApiSeason": None},
    )
    out = await nhl.update_teams(client=mock_client)
    assert out is nhl
    assert nhl.season is None
    assert nhl.teams == {}
    get_data.assert_called_once()


@pytest.mark.asyncio
async def test_nhl_update_teams(
    nhl_nba_teams_payload: list[dict],
    mock_client: AsyncClient,
    mocker: MockerFixture,
) -> None:
    """Test NHL team updates."""
    nhl = NHL(settings=settings.providers.sports)

    current_season = {"ApiSeason": "2026PRE"}
    get_data = mocker.patch(
        "merino.providers.suggest.sports.backends.sportsdata.common.sports.get_data",
        side_effect=[current_season, nhl_nba_teams_payload],
    )
    await nhl.update_teams(client=mock_client)
    assert nhl.season == "2026PRE"
    assert set(nhl.teams.keys()) == {30000007, 30000024}
    assert get_data.call_count == 2


@pytest.mark.asyncio
async def test_nba_update_teams(
    nhl_nba_teams_payload: list[dict], mock_client: AsyncClient, mocker: MockerFixture
) -> None:
    """Test NHL team updates."""
    nba = NBA(settings=settings.providers.sports)
    current_season = {"ApiSeason": "2026PRE"}
    get_data = mocker.patch(
        "merino.providers.suggest.sports.backends.sportsdata.common.sports.get_data",
        side_effect=[current_season, nhl_nba_teams_payload],
    )
    await nba.update_teams(client=mock_client)
    assert nba.season == "2026PRE"
    assert set(nba.teams.keys()) == {30000007, 30000024}
    assert get_data.call_count == 2


@freezegun.freeze_time("2025-09-22T00:00:00", tz_offset=0)
@pytest.mark.asyncio
async def test_ucl_update_teams(
    nhl_nba_teams_payload: list[dict], mock_client: AsyncClient, mocker: MockerFixture
) -> None:
    """Test ucl team updates."""
    ucl = UCL(settings=settings.providers.sports)
    get_data = mocker.patch(
        "merino.providers.suggest.sports.backends.sportsdata.common.sports.get_data",
        side_effect=[
            nhl_nba_teams_payload,
            nhl_nba_teams_payload,
        ],  # called twice per code
    )
    await ucl.update_teams(client=mock_client)
    assert ucl.season == "2025"
    assert set(ucl.teams.keys()) == {30000007, 30000024}
    assert get_data.call_count == 1

    assert "/Teams/ucl?key=" in get_data.call_args_list[0].kwargs["url"]


@freezegun.freeze_time("2025-09-22T00:00:00", tz_offset=0)
@pytest.mark.asyncio
async def test_nfl_update_events(
    nfl_teams_payload: list[dict],
    nfl_scores_payload: list[dict[str, Any]],
    mock_client: AsyncClient,
    mocker: MockerFixture,
) -> None:
    """Test NFL event updates."""
    nfl = NFL(settings=settings.providers.sports)
    nfl.load_teams_from_source(nfl_teams_payload)
    nfl.season = "2025REG"
    nfl.week = 3
    nfl.event_ttl = timedelta(weeks=2)

    get_data = mocker.patch(
        "merino.providers.suggest.sports.backends.sportsdata.common.sports.get_data",
        side_effect=[nfl_scores_payload, nfl_scores_payload[:0]],
    )

    await nfl.update_events(client=mock_client)
    assert 19047 in nfl.events
    assert 22222 not in nfl.events
    ev = nfl.events[19047]
    assert ev.status == GameStatus.Scheduled
    assert ev.home_team["key"] == "PIT"
    assert ev.away_team["key"] == "MIN"
    assert isinstance(json.loads(ev.model_dump_json())["expiry"], str)
    assert get_data.call_count == 2


@pytest.mark.asyncio
async def test_nfl_update_events_with_bad_date_time(
    nfl_teams_payload: list[dict],
    nfl_scores_payload: list[dict[str, Any]],
    mock_client: AsyncClient,
    mocker: MockerFixture,
) -> None:
    """Test NFL event updates."""
    nfl = NFL(settings=settings.providers.sports)
    nfl.load_teams_from_source(nfl_teams_payload)
    nfl.season = "2025REG"
    nfl.week = 3
    nfl.event_ttl = timedelta(weeks=2)
    nfl_scores_payload_copy = nfl_scores_payload.copy()
    for payload in nfl_scores_payload_copy:
        payload["DateTimeUTC"] = 20250101
    get_data = mocker.patch(
        "merino.providers.suggest.sports.backends.sportsdata.common.sports.get_data",
        side_effect=[nfl_scores_payload_copy, nfl_scores_payload_copy[:0]],
    )

    await nfl.update_events(client=mock_client)
    assert len(list(nfl.events)) == 0
    assert get_data.call_count == 2


@freezegun.freeze_time("2025-09-22T00:00:00", tz_offset=0)
@pytest.mark.asyncio
async def test_nhl_update_events(
    nhl_nba_teams_payload: list[dict],
    schedules_payload: list[dict],
    mock_client: AsyncClient,
    mocker: MockerFixture,
) -> None:
    """Test NHL event updates."""
    nhl = NHL(settings=settings.providers.sports)
    nhl.load_teams_from_source(nhl_nba_teams_payload)
    nhl.season = "2026PRE"
    nhl.event_ttl = timedelta(weeks=2)

    get_data = mocker.patch(
        "merino.providers.suggest.sports.backends.sportsdata.common.sports.get_data",
        return_value=schedules_payload,
    )

    await nhl.update_events(client=mock_client)
    assert 30023869 in nhl.events and 0 not in nhl.events
    ev = nhl.events[30023869]
    assert ev.status == GameStatus.Final
    assert ev.home_team["key"] == "TOR"
    assert ev.away_team["key"] == "VAN"
    get_data.assert_called_once()


@freezegun.freeze_time("2025-09-22T00:00:00", tz_offset=0)
@pytest.mark.asyncio
async def test_nba_update_events(
    nhl_nba_teams_payload: list[dict],
    schedules_payload: list[dict],
    mock_client: AsyncClient,
    mocker: MockerFixture,
) -> None:
    """Test NHL event updates."""
    nba = NBA(settings=settings.providers.sports)
    nba.load_teams_from_source(nhl_nba_teams_payload)
    nba.season = "2026PRE"
    nba.event_ttl = timedelta(weeks=2)

    get_data = mocker.patch(
        "merino.providers.suggest.sports.backends.sportsdata.common.sports.get_data",
        return_value=schedules_payload,
    )

    await nba.update_events(client=mock_client)
    assert 30023869 in nba.events and 0 not in nba.events
    assert nba.events[30023869].status == GameStatus.Final
    get_data.assert_called_once()


@freezegun.freeze_time("2025-09-22T00:00:00", tz_offset=0)
@pytest.mark.asyncio
async def test_ucl_update_events(
    nhl_nba_teams_payload: list[dict],
    schedules_payload: list[dict],
    mock_client: AsyncClient,
    mocker: MockerFixture,
) -> None:
    """Test UCL event updates."""
    ucl = UCL(settings=settings.providers.sports)
    ucl.load_teams_from_source(nhl_nba_teams_payload)
    ucl.season = "2025"  # set by update_teams normally
    ucl.event_ttl = timedelta(weeks=2)

    get_data = mocker.patch(
        "merino.providers.suggest.sports.backends.sportsdata.common.sports.get_data",
        return_value=schedules_payload,
    )

    await ucl.update_events(client=mock_client)
    assert 30023869 in ucl.events and 0 not in ucl.events
    assert "/SchedulesBasic/UCL/2025?key=" in get_data.call_args_list[0].kwargs["url"]


@freezegun.freeze_time("2025-09-22T00:00:00", tz_offset=0)
@pytest.mark.asyncio
async def test_weird_afc_update_events(
    nhl_nba_teams_payload: list[dict],
    weird_schedules_payload: list[dict],
    mock_client: AsyncClient,
    mocker: MockerFixture,
) -> None:
    """Test UCL event updates."""
    sport = NFL(settings=settings.providers.sports)
    sport.load_teams_from_source(nhl_nba_teams_payload)
    sport.season = "2025"  # set by update_teams normally
    sport.event_ttl = timedelta(weeks=2)

    mocker.patch(
        "merino.providers.suggest.sports.backends.sportsdata.common.sports.get_data",
        return_value=weird_schedules_payload,
    )
    await sport.update_events(client=mock_client)
    assert not sport.events


@pytest.mark.asyncio
async def test_sportsdata_errors() -> None:
    """Test that the warning and error wrappers work."""
    warning = SportsDataWarning("Foo")
    assert str(warning) == "SportsDataWarning: Foo"

    error = SportsDataError("Foo")
    assert str(error) == "SportsDataError: Foo"
