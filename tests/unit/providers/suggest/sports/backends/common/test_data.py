"""Unit Test for Sports Data models."""

from datetime import datetime

import freezegun
import pytest

from merino.configs import settings
from merino.providers.suggest.sports.backends.sportsdata.common import GameStatus
from merino.providers.suggest.sports.backends.sportsdata.common.data import Team, Sport
from merino.providers.suggest.sports.backends.sportsdata.common.sports import NFL, NHL, NBA


@pytest.fixture
def time_frame_response():
    """Time frame response for testing."""
    return [
        {
            "SeasonType": 1,
            "Season": 2025,
            "Week": 3,
            "Name": "Week 3",
            "ShortName": "Week 3",
            "StartDate": "2025-09-17T00:00:00",
            "EndDate": "2025-09-23T23:59:59",
            "FirstGameStart": "2025-09-18T20:15:00",
            "FirstGameEnd": "2025-09-19T00:15:00",
            "LastGameEnd": "2025-09-23T00:15:00",
            "HasGames": True,
            "HasStarted": True,
            "HasEnded": False,
            "HasFirstGameStarted": True,
            "HasFirstGameEnded": True,
            "HasLastGameEnded": True,
            "ApiSeason": "2025REG",
            "ApiWeek": "3",
        }
    ]


@pytest.fixture
def events_response():
    """Events response for testing."""
    return [
        {
            "GameID": 23869,
            "Season": 2026,
            "SeasonType": 2,
            "Status": "Final",
            "Day": "2025-09-21T00:00:00",
            "DateTime": "2025-09-21T21:30:00",
            "Updated": "2025-09-29T04:10:57",
            "IsClosed": True,
            "AwayTeam": "AWA",
            "HomeTeam": "HOM",
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
        },
        {
            "GameID": 22222,
            "Season": 2000,
            "SeasonType": 2,
            "Status": "Final",
            "Day": "2000-01-01T00:00:00",
            "DateTime": "2025-01-01T21:30:00",
            "Updated": "2025-01-01T04:10:57",
            "IsClosed": True,
            "AwayTeam": "AWA",
            "HomeTeam": "HOM",
            "StadiumID": 9,
            "AwayTeamScore": 0,
            "HomeTeamScore": 0,
            "GlobalGameID": 12312312,
            "GlobalAwayTeamID": 30000041,
            "GlobalHomeTeamID": 30000019,
            "GameEndDateTime": "2000-09-22T00:10:17",
            "NeutralVenue": False,
            "DateTimeUTC": "2000-09-22T01:30:00",
            "AwayTeamID": 41,
            "HomeTeamID": 19,
            "SeriesInfo": None,
        },
    ]


@pytest.fixture(name="home_team")
def home_team_fixture():
    """Home team fixture."""
    return Team(
        fullname="The Home Team",
        terms="Home Team",
        name="Home Team",
        key="HOM",
        locale="AA",
        aliases=["Home Team", "Home", "AA Home Team"],
        colors=[],
        updated=datetime(2025, 9, 21, 10, 30, 00),
        expiry=1760502209,
    )


@pytest.fixture(name="away_team")
def away_team_fixture():
    """Away team fixture."""
    return Team(
        fullname="The Away Team",
        terms="Away Team",
        name="Away Team",
        key="AWA",
        locale="BB",
        aliases=["Away Team", "Away Team", "BB Away Team"],
        colors=[],
        updated=datetime(2025, 9, 22, 10, 30, 00),
        expiry=1760502209,
    )


@pytest.fixture(name="teams")
def teams_fixture():
    """Teams fixture."""
    return [
        {
            "Key": "HOM",
            "Name": "Home",
            "City": "Toronto",
            "AreaName": "HO",
            "FullName": "The Homes",
            "Nickname1": "Home",
            "PrimaryColor": "000000",
            "SecondaryColor": "FFB612",
        },
        {
            "Key": "AWA",
            "Name": "Away",
            "City": "Montreal",
            "AreaName": "AW",
            "FullName": "The Aways",
            "PrimaryColor": "00205B",
            "SecondaryColor": "41B6E6",
        },
    ]


@freezegun.freeze_time("2025-09-22T00:00:00", tz_offset=0)
@pytest.mark.parametrize("sport_cls", [NFL, NHL, NBA], ids=["NFL", "NHL", "NBA"])
def test_load_schedules_from_source_filters_and_populates(
    sport_cls: type[Sport],
    events_response: list[dict],
    home_team: Team,
    away_team: Team,
):
    """Ensure Load scores from source filters and returns relevant events."""
    sport = sport_cls(settings=settings.providers.sports)
    sport.teams = {
        "HOM": home_team,
        "AWA": away_team,
    }

    events = sport.load_schedules_from_source(events_response)

    assert 30023869 in events
    assert 12312312 not in events

    ev = events[30023869]

    assert ev.status == GameStatus.Final
    assert ev.home_team["key"] == "HOM"
    assert ev.away_team["key"] == "AWA"
    assert ev.home_score == 3
    assert ev.away_score == 2

    assert ev.suggest_title() == "The Away Team at The Home Team"
    assert ev.suggest_description() == "Final score: 2 - 3"


@freezegun.freeze_time("2025-09-22T00:00:00", tz_offset=0)
@pytest.mark.parametrize("sport_cls", [NFL, NHL, NBA], ids=["NFL", "NHL", "NBA"])
def test_load_teams_from_source(
    sport_cls: type[Sport],
    events_response: list[dict],
    teams: list[dict],
    home_team: Team,
    away_team: Team,
):
    """Ensure teams are loaded correctly."""
    sport = sport_cls(settings=settings.providers.sports)
    teams_data = sport.load_teams_from_source(teams)

    assert set(teams_data.keys()) == {"AWA", "HOM"}
