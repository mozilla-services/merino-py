"""Unit Tests for Sports."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from importlib.resources import files
from unittest.mock import MagicMock, call
from typing import Any, cast
from zoneinfo import ZoneInfo

import freezegun
import orjson
import pytest
from httpx import AsyncClient
from pytest_mock import MockerFixture

from merino.configs import settings
from merino.cache.redis import RedisAdapter
from merino.providers.suggest.sports.backends.sportsdata.common.data import Event, Sport, Team
from merino.providers.suggest.sports.backends.sportsdata.common.error import (
    SportsDataError,
    SportsDataWarning,
)
from merino.providers.suggest.sports.backends.sportsdata.common import GameStatus
from merino.providers.suggest.sports.backends.sportsdata.common.wcs_elimination import (
    eliminated_team_keys_cache_key,
)
import merino.providers.suggest.sports.backends.sportsdata.common.sports as sports_module
from merino.providers.suggest.sports.backends.sportsdata.common.sports import (
    NFL,
    NHL,
    NBA,
    UCL,
    MLB,
    WCS,
    SPORT_CATEGORY_MAP,
)


@pytest.fixture
def mock_client(mocker: MockerFixture) -> AsyncClient:
    """Mock Async Client."""
    return cast(AsyncClient, mocker.Mock(spec=AsyncClient))


# **NOTE**: The provider is not very consistent about data values, or key names
# It is, therefore, important to use samples taken directly from their API
# in order to validate our testing. The following are truncated versions of the
# various API calls. Some values have been modified from JSON to Python.


def nfl_teams_payload() -> list[dict]:
    """NFL team payload.

    Team Profiles (Basic)
    See https://api.sportsdata.io/v3/nfl/scores/json/TeamsBasic
    """
    return [
        {
            "Key": "ARI",
            "TeamID": 1,
            "PlayerID": 1,
            "City": "Arizona",
            "Name": "Cardinals",
            "Conference": "NFC",
            "Division": "West",
            "FullName": "Arizona Cardinals",
            "StadiumID": 29,
            "ByeWeek": 8,
            "GlobalTeamID": 1,
            "HeadCoach": "Mike LaFleur",
            "PrimaryColor": "97233F",
            "SecondaryColor": "FFFFFF",
            "TertiaryColor": "000000",
            "QuaternaryColor": "A5ACAF",
            "WikipediaLogoURL": "https://upload.wikimedia.org/wikipedia/en/7/72/Arizona_Cardinals_logo.svg",
            "WikipediaWordMarkURL": "https://upload.wikimedia.org/wikipedia/commons/0/04/Arizona_Cardinals_wordmark.svg",
            "OffensiveCoordinator": "Nathaniel Hackett",
            "DefensiveCoordinator": "Nick Rallis",
            "SpecialTeamsCoach": "Michael Ghobrial",
            "OffensiveScheme": "3WR",
            "DefensiveScheme": "3-4",
        },
        {
            "Key": "ATL",
            "TeamID": 2,
            "PlayerID": 2,
            "City": "Atlanta",
            "Name": "Falcons",
            "Conference": "NFC",
            "Division": "South",
            "FullName": "Atlanta Falcons",
            "StadiumID": 45,
            "ByeWeek": 5,
            "GlobalTeamID": 2,
            "HeadCoach": "Kevin Stefanski",
            "PrimaryColor": "000000",
            "SecondaryColor": "A71930",
            "TertiaryColor": "A5ACAF",
            "QuaternaryColor": "FFFFFF",
            "WikipediaLogoURL": "https://upload.wikimedia.org/wikipedia/en/c/c5/Atlanta_Falcons_logo.svg",
            "WikipediaWordMarkURL": "https://upload.wikimedia.org/wikipedia/commons/e/ec/Atlanta_Falcons_wordmark.svg",
            "OffensiveCoordinator": "Tommy Rees",
            "DefensiveCoordinator": "Jeff Ulbrich",
            "SpecialTeamsCoach": "Craig Aukerman",
            "OffensiveScheme": "3WR",
            "DefensiveScheme": "3-4",
        },
    ]


def nfl_schedule_payload() -> list[dict]:
    """Return an NFL formatted schedule item

    See https://sportsdata.io/developers/data-dictionary/nfl#schedulebasic
    """
    return [
        {
            "GameID": 11111,
            "GlobalGameID": 11111,
            "ScoreID": 11111,
            "GameKey": "202510126",
            "Season": 2025,
            "SeasonType": 1,
            "Status": "Final",
            "Canceled": False,
            "Date": "2025-09-04T20:20:00",
            "Day": "2025-09-04T00:00:00",
            "DateTime": "2025-09-04T20:20:00",
            "DateTimeUTC": "2025-09-05T00:20:00",
            "AwayTeam": "ARI",
            "HomeTeam": "ATL",
            "GlobalAwayTeamID": 2,
            "GlobalHomeTeamID": 1,
            "AwayTeamID": 2,
            "HomeTeamID": 1,
            "StadiumID": 18,
            "Closed": None,
            "LastUpdated": None,
            "IsClosed": None,
            "Week": 1,
            "RescheduledFromGameID": None,
            "RescheduledGameID": None,
        },
        {
            "GameID": 22222,
            "GlobalGameID": 22222,
            "ScoreID": 22222,
            "GameKey": "202510129",
            "Season": 2025,
            "SeasonType": 1,
            "Status": "Final",
            "Canceled": False,
            "Date": "2025-09-05T20:00:00",
            "Day": "2025-09-05T00:00:00",
            "DateTime": "2025-09-05T20:00:00",
            "DateTimeUTC": "2025-09-06T00:00:00",
            "AwayTeam": "ATL",
            "HomeTeam": "ARI",
            "GlobalAwayTeamID": 1,
            "GlobalHomeTeamID": 2,
            "AwayTeamID": 1,
            "HomeTeamID": 2,
            "StadiumID": 87,
            "Closed": None,
            "LastUpdated": None,
            "IsClosed": None,
            "Week": 1,
            "RescheduledFromGameID": None,
            "RescheduledGameID": None,
        },
    ]


def nfl_test_scores_payload() -> list[dict[str, Any]]:
    """Test NFL scores payload."""
    within = "2025-09-22T13:30:00"  # UTC
    outside = "2026-01-22T13:30:00"
    games = nfl_scores_payload()
    games[0].update(
        {
            "GlobalGameID": 11111,
            "GameID": 11111,
            "Date": "2025-09-22T09:30:00",
            "Day": "2025-09-22T00:00:00",
            "DateTime": "2025-09-22T09:30:00",
            "DateTimeUTC": within,
            "Status": "Scheduled",
            "AwayTeam": "ARI",
            "HomeTeam": "ATL",
            "GlobalAwayTeamID": 1,
            "GlobalHomeTeamID": 2,
        }
    )
    games[1].update(
        {
            "GlobalGameID": 22222,
            "GameID": 22222,
            "Date": "2026-01-22T09:30:00",
            "Day": "2026-01-22T00:00:00",
            "DateTime": "2026-01-22T09:30:00",
            "DateTimeUTC": outside,
            "AwayTeam": "ATL",
            "HomeTeam": "ARI",
            "GlobalAwayTeamID": 2,
            "GlobalHomeTeamID": 1,
        }
    )
    return games


def nfl_scores_payload() -> list[dict]:
    """Return a sample of NFL scores

    See https://sportsdata.io/developers/data-dictionary/nfl#scorebasic
    """
    return [
        {
            "Quarter": "F",
            "TimeRemaining": None,
            "QuarterDescription": "Final",
            "GameEndDateTime": "2025-12-25T23:01:54",
            "AwayScore": 20,
            "HomeScore": 13,
            "GameID": 11111,
            "GlobalGameID": 11111,
            "ScoreID": 11111,
            "GameKey": "202511716",
            "Season": 2025,
            "SeasonType": 1,
            "Status": "Final",
            "Canceled": False,
            "Date": "2025-12-25T20:15:00",
            "Day": "2025-12-25T00:00:00",
            "DateTime": "2025-12-25T20:15:00",
            "DateTimeUTC": "2025-12-26T01:15:00",
            "AwayTeam": "ARI",
            "HomeTeam": "ATL",
            "GlobalAwayTeamID": 1,
            "GlobalHomeTeamID": 2,
            "AwayTeamID": 1,
            "HomeTeamID": 2,
            "StadiumID": 15,
            "Closed": True,
            "LastUpdated": "2025-12-30T22:56:25",
            "IsClosed": True,
            "Week": 17,
            "RescheduledFromGameID": None,
            "RescheduledGameID": None,
        },
        {
            "Quarter": "F",
            "TimeRemaining": None,
            "QuarterDescription": "Final",
            "GameEndDateTime": "2025-12-25T16:09:12",
            "AwayScore": 30,
            "HomeScore": 23,
            "GameID": 22222,
            "GlobalGameID": 22222,
            "ScoreID": 22222,
            "GameKey": "202511735",
            "Season": 2025,
            "SeasonType": 1,
            "Status": "Final",
            "Canceled": False,
            "Date": "2025-12-25T13:00:00",
            "Day": "2025-12-25T00:00:00",
            "DateTime": "2025-12-25T13:00:00",
            "DateTimeUTC": "2025-12-25T18:00:00",
            "AwayTeam": "ARI",
            "HomeTeam": "ATL",
            "GlobalAwayTeamID": 2,
            "GlobalHomeTeamID": 1,
            "AwayTeamID": 2,
            "HomeTeamID": 1,
            "StadiumID": 19,
            "Closed": True,
            "LastUpdated": "2025-12-30T22:56:25",
            "IsClosed": True,
            "Week": 17,
            "RescheduledFromGameID": None,
            "RescheduledGameID": None,
        },
    ]


def nba_teams_payload() -> list[dict]:
    """NBA team payload.

    Team Profiles - by Active
    See https://sportsdata.io/developers/api-documentation/nba#team-profiles--by-active
    """
    return [
        {
            "TeamID": 1,
            "Key": "WAS",
            "Active": True,
            "City": "Washington",
            "Name": "Wizards",
            "LeagueID": 3,
            "StadiumID": 1,
            "Conference": "Eastern",
            "Division": "Southeast",
            "PrimaryColor": "002B5C",
            "SecondaryColor": "E31837",
            "TertiaryColor": "C4CED4",
            "QuaternaryColor": "FFFFFF",
            "WikipediaLogoUrl": "https://upload.wikimedia.org/wikipedia/en/0/02/Washington_Wizards_logo.svg",
            "WikipediaWordMarkUrl": None,
            "GlobalTeamID": 20000001,
            "NbaDotComTeamID": 1610612764,
            "HeadCoach": "Brian Keefe",
        },
        {
            "TeamID": 2,
            "Key": "CHA",
            "Active": True,
            "City": "Charlotte",
            "Name": "Hornets",
            "LeagueID": 3,
            "StadiumID": 2,
            "Conference": "Eastern",
            "Division": "Southeast",
            "PrimaryColor": "00788C",
            "SecondaryColor": "1D1160",
            "TertiaryColor": "A1A1A4",
            "QuaternaryColor": "FFFFFF",
            "WikipediaLogoUrl": "https://upload.wikimedia.org/wikipedia/en/c/c4/Charlotte_Hornets_%282014%29.svg",
            "WikipediaWordMarkUrl": None,
            "GlobalTeamID": 20000002,
            "NbaDotComTeamID": 1610612766,
            "HeadCoach": "Charles Lee",
        },
    ]


def nba_schedule_payload() -> list[dict]:
    """Return an NBA formatted schedule item

    See https://sportsdata.io/developers/data-dictionary/nba#schedulebasic
    """
    return [
        {
            "GameID": 11111,
            "Season": 2025,
            "SeasonType": 1,
            "Status": "Final",
            "Day": "2024-10-22T00:00:00",
            "DateTime": "2024-10-22T19:30:00",
            "AwayTeam": "WAS",
            "HomeTeam": "CHA",
            "AwayTeamID": 1,
            "HomeTeamID": 2,
            "StadiumID": 9,
            "AwayTeamScore": None,
            "HomeTeamScore": None,
            "Updated": "2026-04-16T10:02:20",
            "GlobalGameID": 20011111,
            "GlobalAwayTeamID": 20000001,
            "GlobalHomeTeamID": 20000002,
            "IsClosed": True,
            "NeutralVenue": False,
            "DateTimeUTC": "2024-10-22T23:30:00",
            "GameEndDateTIme": "2024-10-22T21:41:05",
            "RescheduledFromGameID": None,
            "RescheduledGameID": None,
        },
        {
            "GameID": 22222,
            "Season": 2025,
            "SeasonType": 1,
            "Status": "Final",
            "Day": "2024-10-22T00:00:00",
            "DateTime": "2024-10-22T22:00:00",
            "AwayTeam": "CHA",
            "HomeTeam": "WAS",
            "AwayTeamID": 2,
            "HomeTeamID": 1,
            "StadiumID": 27,
            "AwayTeamScore": None,
            "HomeTeamScore": None,
            "Updated": "2026-04-16T10:02:20",
            "GlobalGameID": 20022222,
            "GlobalAwayTeamID": 20000002,
            "GlobalHomeTeamID": 20000001,
            "IsClosed": True,
            "NeutralVenue": False,
            "DateTimeUTC": "2024-10-23T02:00:00",
            "GameEndDateTIme": "2024-10-23T00:34:03",
            "RescheduledFromGameID": None,
            "RescheduledGameID": None,
        },
    ]


def nba_score_payload() -> list[dict]:
    """Return a sample NBA score items

    See https://sportsdata.io/developers/api-documentation/nba#games-basic--by-date-live--final
    """
    return [
        {
            "GameEndDateTime": "2025-12-01T21:20:58",
            "GameID": 11111,
            "Season": 2026,
            "SeasonType": 1,
            "Status": "Final",
            "Day": "2025-12-01T00:00:00",
            "DateTime": "2025-12-01T19:00:00",
            "AwayTeam": "WAS",
            "HomeTeam": "CHA",
            "AwayTeamID": 1,
            "HomeTeamID": 2,
            "StadiumID": 14,
            "AwayTeamScore": 98,
            "HomeTeamScore": 99,
            "Updated": "2025-12-01T21:31:42",
            "GlobalGameID": 20011111,
            "GlobalAwayTeamID": 20000001,
            "GlobalHomeTeamID": 20000002,
            "IsClosed": True,
            "NeutralVenue": False,
            "DateTimeUTC": "2025-12-02T00:00:00",
            "GameEndDateTIme": "2025-12-01T21:20:58",
            "RescheduledFromGameID": None,
            "RescheduledGameID": None,
            "SeriesInfo": None,
        },
        {
            "GameEndDateTime": "2025-12-01T21:37:02",
            "GameID": 22222,
            "Season": 2026,
            "SeasonType": 1,
            "Status": "Final",
            "Day": "2025-12-01T00:00:00",
            "DateTime": "2025-12-01T19:00:00",
            "AwayTeam": "CHA",
            "HomeTeam": "WAS",
            "AwayTeamID": 2,
            "HomeTeamID": 1,
            "StadiumID": 13,
            "AwayTeamScore": 135,
            "HomeTeamScore": 119,
            "Updated": "2025-12-01T21:46:58",
            "GlobalGameID": 20022222,
            "GlobalAwayTeamID": 20000002,
            "GlobalHomeTeamID": 20000001,
            "IsClosed": True,
            "NeutralVenue": False,
            "DateTimeUTC": "2025-12-02T00:00:00",
            "GameEndDateTIme": "2025-12-01T21:37:02",
            "RescheduledFromGameID": None,
            "RescheduledGameID": None,
            "SeriesInfo": None,
        },
    ]


def nhl_teams_payload() -> list[dict]:
    """NHL team payload.

    Team Profiles - by Active
    https://sportsdata.io/developers/api-documentation/nhl#team-profiles--by-active
    """
    return [
        {
            "TeamID": 1,
            "Key": "BOS",
            "Active": True,
            "City": "Boston",
            "Name": "Bruins",
            "StadiumID": 3,
            "Conference": "Eastern",
            "Division": "Atlantic",
            "PrimaryColor": "010101",
            "SecondaryColor": "FFB81C",
            "TertiaryColor": "FFFFFF",
            "QuaternaryColor": None,
            "WikipediaLogoUrl": "https://upload.wikimedia.org/wikipedia/commons/0/02/Boston_Bruins_100th_anniversary_logo.svg",
            "WikipediaWordMarkUrl": None,
            "GlobalTeamID": 30000001,
            "HeadCoach": "Marco Sturm",
        },
        {
            "TeamID": 2,
            "Key": "BUF",
            "Active": True,
            "City": "Buffalo",
            "Name": "Sabres",
            "StadiumID": 4,
            "Conference": "Eastern",
            "Division": "Atlantic",
            "PrimaryColor": "003087",
            "SecondaryColor": "FFB81C",
            "TertiaryColor": "FFFFFF",
            "QuaternaryColor": None,
            "WikipediaLogoUrl": "https://upload.wikimedia.org/wikipedia/en/9/9e/Buffalo_Sabres_Logo.svg",
            "WikipediaWordMarkUrl": None,
            "GlobalTeamID": 30000002,
            "HeadCoach": "Lindy Ruff",
        },
    ]


def nhl_schedule_payload() -> list[dict]:
    """Return an NHL formatted schedule item

    See https://sportsdata.io/developers/data-dictionary/nhl#schedulebasic
    """
    return [
        {
            "GameID": 11111,
            "Season": 2025,
            "SeasonType": 1,
            "Status": "Final",
            "Day": "2024-10-04T00:00:00",
            "DateTime": "2024-10-04T13:00:00",
            "Updated": "2024-10-04T22:59:21",
            "IsClosed": True,
            "AwayTeam": "BOS",
            "HomeTeam": "BUF",
            "StadiumID": 40,
            "AwayTeamScore": None,
            "HomeTeamScore": None,
            "GlobalGameID": 30011111,
            "GlobalAwayTeamID": 30000001,
            "GlobalHomeTeamID": 30000002,
            "GameEndDateTime": "2024-10-04T15:42:55",
            "NeutralVenue": True,
            "DateTimeUTC": "2024-10-04T17:00:00",
            "AwayTeamID": 1,
            "HomeTeamID": 2,
            "RescheduledFromGameID": None,
            "RescheduledGameID": None,
            "SeriesInfo": None,
        },
        {
            "GameID": 22222,
            "Season": 2025,
            "SeasonType": 1,
            "Status": "Final",
            "Day": "2024-10-05T00:00:00",
            "DateTime": "2024-10-05T10:00:00",
            "Updated": "2024-10-05T13:12:52",
            "IsClosed": True,
            "AwayTeam": "BUF",
            "HomeTeam": "BOS",
            "StadiumID": 40,
            "AwayTeamScore": None,
            "HomeTeamScore": None,
            "GlobalGameID": 30022222,
            "GlobalAwayTeamID": 30000002,
            "GlobalHomeTeamID": 30000001,
            "GameEndDateTime": "2024-10-05T12:43:27",
            "NeutralVenue": True,
            "DateTimeUTC": "2024-10-05T14:00:00",
            "AwayTeamID": 2,
            "HomeTeamID": 1,
            "RescheduledFromGameID": None,
            "RescheduledGameID": None,
            "SeriesInfo": None,
        },
    ]


def nhl_score_payload() -> list[dict]:
    """Return a sample NHL score item"""
    return [
        {
            "GameID": 11111,
            "Season": 2026,
            "SeasonType": 2,
            "Status": "Final",
            "Day": "2025-09-25T00:00:00",
            "DateTime": "2025-09-25T19:00:00",
            "Updated": "2025-09-25T21:54:14",
            "IsClosed": True,
            "AwayTeam": "BOS",
            "HomeTeam": "BUF",
            "AwayTeamID": 1,
            "HomeTeamID": 2,
            "StadiumID": 29,
            "AwayTeamScore": 1,
            "HomeTeamScore": 5,
            "GameEndDateTime": "2025-09-25T21:47:45",
            "DateTimeUTC": "2025-09-25T23:00:00",
        },
        {
            "GameID": 22222,
            "Season": 2026,
            "SeasonType": 2,
            "Status": "Final",
            "Day": "2025-09-25T00:00:00",
            "DateTime": "2025-09-25T19:00:00",
            "Updated": "2025-09-25T22:55:33",
            "IsClosed": True,
            "AwayTeam": "BUF",
            "HomeTeam": "BOS",
            "AwayTeamID": 2,
            "HomeTeamID": 1,
            "StadiumID": 16,
            "AwayTeamScore": 7,
            "HomeTeamScore": 2,
            "GameEndDateTime": "2025-09-25T21:39:39",
            "DateTimeUTC": "2025-09-25T23:00:00",
        },
    ]


def nhl_test_scores_payload() -> list[dict[str, Any]]:
    """Test NHL scores payload."""
    within = "2025-09-22T13:30:00"  # UTC
    outside = "2026-01-22T13:30:00"
    games = nfl_scores_payload()
    games[0].update(
        {
            "Date": within,
            "Day": within,
            "DateTime": within,
            "DateTimeUTC": within,
            "Status": "Scheduled",
        }
    )
    games[1].update(
        {
            "Date": outside,
            "Day": outside,
            "DateTime": outside,
            "DateTimeUTC": outside,
            "Status": "Scheduled",
        }
    )
    return games


def mlb_teams_payload() -> list[dict]:
    """Return the MLB team profile"""
    return [
        {
            "TeamID": 1,
            "Key": "LAD",
            "Active": True,
            "City": "Los Angeles",
            "Name": "Dodgers",
            "StadiumID": 31,
            "League": "NL",
            "Division": "West",
            "PrimaryColor": "005A9C",
            "SecondaryColor": "FFFFFF",
            "TertiaryColor": "EF3E42",
            "QuaternaryColor": None,
            "WikipediaLogoUrl": "https://upload.wikimedia.org/wikipedia/commons/0/0e/Los_Angeles_Dodgers_Logo.svg",
            "WikipediaWordMarkUrl": "https://upload.wikimedia.org/wikipedia/commons/f/f6/LA_Dodgers.svg",
            "GlobalTeamID": 10000001,
            "HeadCoach": "Dave Roberts",
            "HittingCoach": "Aaron Bates & Robert Van Scoyoc",
            "PitchingCoach": "Mark Prior",
        },
        {
            "TeamID": 2,
            "Key": "CIN",
            "Active": True,
            "City": "Cincinnati",
            "Name": "Reds",
            "StadiumID": 64,
            "League": "NL",
            "Division": "Central",
            "PrimaryColor": "C6011F",
            "SecondaryColor": "000000",
            "TertiaryColor": "FFFFFF",
            "QuaternaryColor": None,
            "WikipediaLogoUrl": "https://upload.wikimedia.org/wikipedia/commons/0/01/Cincinnati_Reds_Logo.svg",
            "WikipediaWordMarkUrl": "https://upload.wikimedia.org/wikipedia/commons/7/71/Cincinnati_Reds_Cap_Insignia.svg",
            "GlobalTeamID": 10000002,
            "HeadCoach": "Terry Francona",
            "HittingCoach": "Chris Valaika",
            "PitchingCoach": "Derek Johnson",
        },
    ]


def mlb_schedule_payload() -> list[dict]:
    """Return an MLB formatted schedule item"""
    return [
        {
            "GameID": 11111,
            "Season": 2025,
            "SeasonType": 1,
            "Status": "Final",
            "Day": "2025-03-18T00:00:00",
            "DateTime": "2025-03-18T06:10:00",
            "AwayTeam": "LAD",
            "HomeTeam": "CIN",
            "AwayTeamID": 1,
            "HomeTeamID": 2,
            "RescheduledGameID": None,
            "StadiumID": 69,
            "IsClosed": True,
            "Updated": "2025-08-11T11:53:19",
            "GameEndDateTime": "2025-03-18T08:49:15",
            "DateTimeUTC": "2025-03-18T10:10:00",
            "RescheduledFromGameID": None,
            "SuspensionResumeDay": None,
            "SuspensionResumeDateTime": None,
            "SeriesInfo": None,
        },
        {
            "GameID": 22222,
            "Season": 2025,
            "SeasonType": 1,
            "Status": "Final",
            "Day": "2025-03-19T00:00:00",
            "DateTime": "2025-03-19T06:10:00",
            "AwayTeam": "CIN",
            "HomeTeam": "LAD",
            "AwayTeamID": 2,
            "HomeTeamID": 1,
            "RescheduledGameID": None,
            "StadiumID": 69,
            "IsClosed": True,
            "Updated": "2025-07-30T18:13:44",
            "GameEndDateTime": "2025-03-19T08:56:03",
            "DateTimeUTC": "2025-03-19T10:10:00",
            "RescheduledFromGameID": None,
            "SuspensionResumeDay": None,
            "SuspensionResumeDateTime": None,
            "SeriesInfo": None,
        },
    ]


def mlb_score_payload() -> list[dict]:
    """Return a sample MLB score record"""
    return [
        {
            "AwayTeamRuns": 1,
            "HomeTeamRuns": 2,
            "AwayTeamHits": 3,
            "HomeTeamHits": 10,
            "AwayTeamErrors": 1,
            "HomeTeamErrors": 0,
            "Attendance": 24249,
            "GlobalGameID": 10011111,
            "GlobalAwayTeamID": 10000001,
            "GlobalHomeTeamID": 10000002,
            "NeutralVenue": False,
            "Inning": 9,
            "InningHalf": "T",
            "GameID": 11111,
            "Season": 2025,
            "SeasonType": 1,
            "Status": "Final",
            "Day": "2025-09-25T00:00:00",
            "DateTime": "2025-09-25T12:40:00",
            "AwayTeam": "LAD",
            "HomeTeam": "CIN",
            "AwayTeamID": 1,
            "HomeTeamID": 2,
            "RescheduledGameID": None,
            "StadiumID": 64,
            "IsClosed": True,
            "Updated": "2025-10-25T05:59:18",
            "GameEndDateTime": "2025-09-25T16:19:27",
            "DateTimeUTC": "2025-09-25T16:40:00",
            "RescheduledFromGameID": None,
            "SuspensionResumeDay": None,
            "SuspensionResumeDateTime": None,
            "SeriesInfo": None,
        },
        {
            "AwayTeamRuns": 5,
            "HomeTeamRuns": 6,
            "AwayTeamHits": 15,
            "HomeTeamHits": 9,
            "AwayTeamErrors": 1,
            "HomeTeamErrors": 0,
            "Attendance": 16777,
            "GlobalGameID": 10022222,
            "GlobalAwayTeamID": 10000002,
            "GlobalHomeTeamID": 10000001,
            "NeutralVenue": False,
            "Inning": 9,
            "InningHalf": "B",
            "GameID": 22222,
            "Season": 2025,
            "SeasonType": 1,
            "Status": "Final",
            "Day": "2025-09-25T00:00:00",
            "DateTime": "2025-09-25T13:05:00",
            "AwayTeam": "LAD",
            "HomeTeam": "CIN",
            "AwayTeamID": 1,
            "HomeTeamID": 2,
            "RescheduledGameID": None,
            "StadiumID": 22,
            "IsClosed": True,
            "Updated": "2025-10-25T05:58:22",
            "GameEndDateTime": "2025-09-25T16:01:10",
            "DateTimeUTC": "2025-09-25T17:05:00",
            "RescheduledFromGameID": None,
            "SuspensionResumeDay": None,
            "SuspensionResumeDateTime": None,
            "SeriesInfo": None,
        },
    ]


def soccer_teams_payload() -> list[dict]:
    """Test Soccer team payload"""
    return [
        {
            "TeamId": 1,
            "AreaId": 68,
            "VenueId": 2,
            "Key": "ARS",
            "Name": "Arsenal FC",
            "FullName": "Arsenal Football Club ",
            "Active": True,
            "AreaName": "England",
            "VenueName": "Emirates Stadium",
            "Gender": "Male",
            "Type": "Club",
            "Address": None,
            "City": None,
            "Zip": None,
            "Phone": None,
            "Fax": None,
            "Website": "http://www.arsenal.com",
            "Email": None,
            "Founded": 1886,
            "ClubColor1": "Red",
            "ClubColor2": "White",
            "ClubColor3": None,
            "Nickname1": "The Gunners",
            "Nickname2": None,
            "Nickname3": None,
            "WikipediaLogoUrl": "https://upload.wikimedia.org/wikipedia/en/5/53/Arsenal_FC.svg",
            "WikipediaWordMarkUrl": None,
            "GlobalTeamId": 90000001,
        },
        {
            "TeamId": 2,
            "AreaId": 68,
            "VenueId": 3,
            "Key": "AST",
            "Name": "Aston Villa FC",
            "FullName": "Aston Villa Football Club",
            "Active": True,
            "AreaName": "England",
            "VenueName": "Villa Park",
            "Gender": "Male",
            "Type": "Club",
            "Address": None,
            "City": None,
            "Zip": None,
            "Phone": None,
            "Fax": None,
            "Website": "http://www.avfc.co.uk",
            "Email": None,
            "Founded": 1874,
            "ClubColor1": "Claret",
            "ClubColor2": "Sky Blue",
            "ClubColor3": None,
            "Nickname1": "The Villa",
            "Nickname2": "The Lions",
            "Nickname3": "The Claret and Blue",
            "WikipediaLogoUrl": "https://upload.wikimedia.org/wikipedia/en/8/86/Aston_Villa_F.C._logo.svg",
            "WikipediaWordMarkUrl": None,
            "GlobalTeamId": 90000002,
        },
    ]


def soccer_schedule_payload() -> list[dict]:
    """Return an generic soccer formatted schedule item

    https://sportsdata.io/developers/data-dictionary/soccer#schedulebasic
    """
    return [
        {
            "GameId": 11111,
            "RoundId": 1499,
            "Season": 2025,
            "SeasonType": 3,
            "Group": None,
            "AwayTeamId": 1,
            "HomeTeamId": 2,
            "VenueId": 9953,
            "Day": "2024-07-09T00:00:00",
            "DateTime": "2024-07-09T15:30:00",
            "Status": "Final",
            "Week": None,
            "Winner": "HomeTeam",
            "VenueType": "Home Away",
            "AwayTeamKey": "ARS",
            "AwayTeamName": "Arsenal FC",
            "AwayTeamCountryCode": "GIB",
            "AwayTeamScore": None,
            "AwayTeamScorePeriod1": None,
            "AwayTeamScorePeriod2": None,
            "AwayTeamScoreExtraTime": None,
            "AwayTeamScorePenalty": None,
            "HomeTeamKey": "AST",
            "HomeTeamName": "Aston Villa FC",
            "HomeTeamCountryCode": "GIB",
            "HomeTeamScore": None,
            "HomeTeamScorePeriod1": None,
            "HomeTeamScorePeriod2": None,
            "HomeTeamScoreExtraTime": None,
            "HomeTeamScorePenalty": None,
            "Updated": "2024-07-10T05:46:08",
            "UpdatedUtc": "2024-07-10T09:46:08",
            "GlobalGameId": 90011111,
            "GlobalAwayTeamId": 90000001,
            "GlobalHomeTeamId": 90000002,
            "IsClosed": True,
            "PlayoffAggregateScore": None,
        },
        {
            "GameId": 22222,
            "RoundId": 1499,
            "Season": 2025,
            "SeasonType": 3,
            "Group": None,
            "AwayTeamId": 2,
            "HomeTeamId": 1,
            "VenueId": 929,
            "Day": "2024-07-09T00:00:00",
            "DateTime": "2024-07-09T16:45:00",
            "Status": "Final",
            "Week": None,
            "Winner": "AwayTeam",
            "VenueType": "Home Away",
            "AwayTeamKey": "AST",
            "AwayTeamName": "Aston Villa FC",
            "AwayTeamCountryCode": "GIB",
            "AwayTeamScore": None,
            "AwayTeamScorePeriod1": None,
            "AwayTeamScorePeriod2": None,
            "AwayTeamScoreExtraTime": None,
            "AwayTeamScorePenalty": None,
            "HomeTeamKey": "ARS",
            "HomeTeamName": "Arsenal FC",
            "HomeTeamCountryCode": "GIB",
            "HomeTeamScore": None,
            "HomeTeamScorePeriod1": None,
            "HomeTeamScorePeriod2": None,
            "HomeTeamScoreExtraTime": None,
            "HomeTeamScorePenalty": None,
            "Updated": "2024-07-10T05:45:56",
            "UpdatedUtc": "2024-07-10T09:45:56",
            "GlobalGameId": 90022222,
            "GlobalAwayTeamId": 90000002,
            "GlobalHomeTeamId": 90000001,
            "IsClosed": True,
            "PlayoffAggregateScore": None,
        },
    ]


def soccer_score_payload() -> list[dict]:
    """Return a sample soccer score record"""
    return [
        {
            "GameId": 11111,
            "RoundId": 1708,
            "Season": 2026,
            "SeasonType": 3,
            "Group": None,
            "AwayTeamId": 1,
            "HomeTeamId": 2,
            "VenueId": 332,
            "Day": "2025-07-09T00:00:00",
            "DateTime": "2025-07-09T16:00:00",
            "Status": "Final",
            "Week": None,
            "Period": "Regular",
            "Clock": None,
            "Winner": "HomeTeam",
            "VenueType": "Home Away",
            "AwayTeamKey": "ARS",
            "AwayTeamName": "Arsenal FC",
            "AwayTeamCountryCode": "GIB",
            "AwayTeamScore": 0,
            "AwayTeamScorePeriod1": 0,
            "AwayTeamScorePeriod2": 0,
            "AwayTeamScoreExtraTime": None,
            "AwayTeamScorePenalty": None,
            "HomeTeamKey": "AST",
            "HomeTeamName": "Aston Village FC",
            "HomeTeamCountryCode": "GIB",
            "HomeTeamScore": 2,
            "HomeTeamScorePeriod1": 0,
            "HomeTeamScorePeriod2": 2,
            "HomeTeamScoreExtraTime": None,
            "HomeTeamScorePenalty": None,
            "HomeTeamMoneyLine": None,
            "AwayTeamMoneyLine": None,
            "DrawMoneyLine": None,
            "PointSpread": None,
            "HomeTeamPointSpreadPayout": None,
            "AwayTeamPointSpreadPayout": None,
            "OverUnder": None,
            "OverPayout": None,
            "UnderPayout": None,
            "Attendance": 3176,
            "Updated": "2025-07-09T16:02:52",
            "UpdatedUtc": "2025-07-09T20:02:52",
            "GlobalGameId": 90011111,
            "GlobalAwayTeamId": 90000001,
            "GlobalHomeTeamId": 90000002,
            "ClockExtra": None,
            "ClockDisplay": "",
            "IsClosed": True,
            "HomeTeamFormation": "4-4-2",
            "AwayTeamFormation": "4-4-1-1",
            "PlayoffAggregateScore": None,
        },
        {
            "GameId": 22222,
            "RoundId": 1708,
            "Season": 2026,
            "SeasonType": 3,
            "Group": None,
            "AwayTeamId": 2372,
            "HomeTeamId": 569,
            "VenueId": 11412,
            "Day": "2025-07-09T00:00:00",
            "DateTime": "2025-07-09T17:30:00",
            "Status": "Final",
            "Week": None,
            "Period": "Regular",
            "Clock": None,
            "Winner": "HomeTeam",
            "VenueType": "Home Away",
            "AwayTeamKey": "AST",
            "AwayTeamName": "Aston Village FC",
            "AwayTeamCountryCode": "GIB",
            "AwayTeamScore": 1,
            "AwayTeamScorePeriod1": 0,
            "AwayTeamScorePeriod2": 1,
            "AwayTeamScoreExtraTime": None,
            "AwayTeamScorePenalty": None,
            "HomeTeamKey": "ARS",
            "HomeTeamName": "Arsenal FC",
            "HomeTeamCountryCode": "GIB",
            "HomeTeamScore": 3,
            "HomeTeamScorePeriod1": 2,
            "HomeTeamScorePeriod2": 1,
            "HomeTeamScoreExtraTime": None,
            "HomeTeamScorePenalty": None,
            "HomeTeamMoneyLine": None,
            "AwayTeamMoneyLine": None,
            "DrawMoneyLine": None,
            "PointSpread": None,
            "HomeTeamPointSpreadPayout": None,
            "AwayTeamPointSpreadPayout": None,
            "OverUnder": None,
            "OverPayout": None,
            "UnderPayout": None,
            "Attendance": 13080,
            "Updated": "2025-07-09T17:20:21",
            "UpdatedUtc": "2025-07-09T21:20:21",
            "GlobalGameId": 90022222,
            "GlobalAwayTeamId": 90000002,
            "GlobalHomeTeamId": 90000001,
            "ClockExtra": None,
            "ClockDisplay": "",
            "IsClosed": True,
            "HomeTeamFormation": "4-1-4-1",
            "AwayTeamFormation": "5-3-2",
            "PlayoffAggregateScore": None,
        },
    ]


def wcs_teams_payload() -> list[dict]:
    """Return WCS sample team data"""
    # https://api.sportsdata.io/v4/soccer/scores/json/Teams/FIFA
    # return soccer_teams_payload()
    return [
        {
            "TeamId": 1,
            "AreaId": 68,
            "VenueId": 199,
            "Key": "ENG",
            "Name": "England",
            "FullName": "The Football Association",
            "Active": True,
            "AreaName": "England",
            "VenueName": "Wembley Stadium connected by EE",
            "Gender": "Male",
            "Type": "National",
            "Address": None,
            "City": None,
            "Zip": None,
            "Phone": None,
            "Fax": None,
            "Website": "https://www.thefa.com",
            "Email": None,
            "Founded": 1863,
            "ClubColor1": "White",
            "ClubColor2": "Red",
            "ClubColor3": "Navy Blue",
            "Nickname1": "The Three Lions",
            "Nickname2": None,
            "Nickname3": None,
            "WikipediaLogoUrl": "https://upload.wikimedia.org/wikipedia/en/b/be/Flag_of_England.svg",
            "WikipediaWordMarkUrl": None,
            "GlobalTeamId": 90000001,
        },
        {
            "TeamId": 2,
            "AreaId": 16,
            "VenueId": 133,
            "Key": "ARG",
            "Name": "Argentina",
            "FullName": "Asociación del Fútbol Argentino",
            "Active": True,
            "AreaName": "Argentina",
            "VenueName": "Estadio Mâs Monumental",
            "Gender": "Male",
            "Type": "National",
            "Address": None,
            "City": None,
            "Zip": None,
            "Phone": None,
            "Fax": None,
            "Website": "http://www.afa.org.ar",
            "Email": None,
            "Founded": 1893,
            "ClubColor1": "Sky Blue",
            "ClubColor2": "White",
            "ClubColor3": "Black",
            "Nickname1": "La Albiceleste",
            "Nickname2": None,
            "Nickname3": None,
            "WikipediaLogoUrl": "https://upload.wikimedia.org/wikipedia/commons/1/1a/Flag_of_Argentina.svg",
            "WikipediaWordMarkUrl": None,
            "GlobalTeamId": 90000002,
        },
    ]


WCS_STATIC_TEAM_IDS = {
    "SWE": 90000001,
    "TUN": 90000002,
}


def wcs_static_teams_payload(keys: set[str]) -> list[dict[str, Any]]:
    """Return WCS team rows with IDs normalized to the checked-in event samples."""
    data = json.loads((files("merino.data") / "wcs_teams.json").read_text())
    teams = []
    for team in data:
        if team["Key"] not in keys:
            continue
        team = dict(team)
        if team["Key"] in WCS_STATIC_TEAM_IDS:
            team["GlobalTeamId"] = WCS_STATIC_TEAM_IDS[team["Key"]]
        teams.append(team)
    return teams


def wcs_static_schedule_payload() -> list[dict[str, Any]]:
    """Return a captured /SchedulesBasic slice with compact team IDs."""
    return cast(
        list[dict[str, Any]],
        json.loads((files("merino.data") / "wcs_schedule.json").read_text()),
    )


def wcs_static_games_by_date_payload() -> list[dict[str, Any]]:
    """Return a captured /GamesByDate slice with compact team IDs."""
    return cast(
        list[dict[str, Any]],
        json.loads((files("merino.data") / "wcs_games_by_date.json").read_text()),
    )


def wcs_schedule_payload() -> list[dict]:
    """Return WCS sample schedule data"""
    # https://api.sportsdata.io/v4/soccer/scores/json/SchedulesBasic/FIFA/2026
    return [
        {
            "GameId": 11111,
            "RoundId": 1615,
            "Season": 2026,
            "SeasonType": 1,
            "Group": "Group A",
            "AwayTeamId": 1,
            "HomeTeamId": 2,
            "VenueId": 420,
            "Day": "2026-06-11T00:00:00",
            "DateTime": "2026-06-11T19:00:00",
            "Status": "Scheduled",
            "Week": 1,
            "Winner": None,
            "VenueType": "Neutral",
            "AwayTeamKey": "RSA",
            "AwayTeamName": "South Africa",
            "AwayTeamCountryCode": "RSA",
            "AwayTeamScore": None,
            "AwayTeamScorePeriod1": None,
            "AwayTeamScorePeriod2": None,
            "AwayTeamScoreExtraTime": None,
            "AwayTeamScorePenalty": None,
            "HomeTeamKey": "MEX",
            "HomeTeamName": "Mexico",
            "HomeTeamCountryCode": "MEX",
            "HomeTeamScore": None,
            "HomeTeamScorePeriod1": None,
            "HomeTeamScorePeriod2": None,
            "HomeTeamScoreExtraTime": None,
            "HomeTeamScorePenalty": None,
            "Updated": "2026-03-23T04:22:23",
            "UpdatedUtc": "2026-03-23T08:22:23",
            "GlobalGameId": 90011111,
            "GlobalAwayTeamId": 90000001,
            "GlobalHomeTeamId": 90000002,
            "IsClosed": False,
            "PlayoffAggregateScore": None,
        },
        {
            "GameId": 22222,
            "RoundId": 1615,
            "Season": 2026,
            "SeasonType": 1,
            "Group": "Group A",
            "AwayTeamId": 945,
            "HomeTeamId": 1209,
            "VenueId": 418,
            "Day": "2026-06-12T00:00:00",
            "DateTime": "2026-06-12T02:00:00",
            "Status": "Scheduled",
            "Week": 1,
            "Winner": None,
            "VenueType": "Neutral",
            "AwayTeamKey": "CZE",
            "AwayTeamName": "Czechia",
            "AwayTeamCountryCode": "CZE",
            "AwayTeamScore": None,
            "AwayTeamScorePeriod1": None,
            "AwayTeamScorePeriod2": None,
            "AwayTeamScoreExtraTime": None,
            "AwayTeamScorePenalty": None,
            "HomeTeamKey": "KOR",
            "HomeTeamName": "Korea Republic",
            "HomeTeamCountryCode": "KOR",
            "HomeTeamScore": None,
            "HomeTeamScorePeriod1": None,
            "HomeTeamScorePeriod2": None,
            "HomeTeamScoreExtraTime": None,
            "HomeTeamScorePenalty": None,
            "Updated": "2026-04-01T04:19:30",
            "UpdatedUtc": "2026-04-01T08:19:30",
            "GlobalGameId": 90022222,
            "GlobalAwayTeamId": 90000002,
            "GlobalHomeTeamId": 90000001,
            "IsClosed": False,
            "PlayoffAggregateScore": None,
        },
    ]


def wcs_score_payload() -> list[dict]:
    """Return WCS sample score data"""
    return soccer_score_payload()


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
            "HomeTeam": "NFC",
            "StadiumID": 9,
            "AwayTeamScore": 2,
            "HomeTeamScore": 3,
            "GlobalGameID": 30023869,
            "GlobalAwayTeamID": 30000098,
            "GlobalHomeTeamID": 30000099,
            "GameEndDateTime": "2025-09-22T00:10:17",
            "NeutralVenue": False,
            "DateTimeUTC": "2025-09-22T01:30:00",
            "AwayTeamID": 98,
            "HomeTeamID": 99,
            "SeriesInfo": None,
        }
    ]


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
def generic_schedules_payload() -> list[dict]:
    """Provide Generic team Schedules payload that are out and in window."""
    return [
        {
            "GameId": 67890,
            "Season": 2026,
            "SeasonType": 2,
            "Status": "Final",
            "Day": "2025-09-21T00:00:00",
            "DateTime": "2025-09-21T21:30:00",
            "DateTimeUTC": "2025-09-21T21:30:00",
            "Updated": "2025-09-29T04:10:57",
            "UpdatedUTC": "2025-09-29T04:10:57",
            "IsClosed": True,
            "AwayTeam": "AWY",
            "HomeTeam": "HOM",
            "AwayTeamKey": "AWY",
            "HomeTeamKey": "HOM",
            "StadiumID": 9,
            "AwayScore": 2,
            "AwayTeamScore": 2,
            "HomeScore": 3,
            "HomeTeamScore": 3,
            "GlobalGameID": 12345678,
            "GlobalAwayTeamID": 99,
            "GlobalHomeTeamID": 98,
            "GameEndDateTime": "2025-09-22T00:10:17",
            "NeutralVenue": False,
            "AwayTeamID": 99,
            "HomeTeamID": 98,
            "SeriesInfo": None,
        },
        {
            "GameId": 11111,
            "Season": 2000,
            "SeasonType": 2,
            "Status": "Final",
            "Day": "2000-01-01T00:00:00",
            "DateTime": "2000-01-01T21:30:00",
            "DateTimeUTC": "2000-01-01T21:30:00",
            "Updated": "2000-01-01T04:10:57",
            "UpdatedUTC": "2000-01-01T04:10:57",
            "IsClosed": True,
            "AwayTeam": "AWY",
            "AwayTeamKey": "AWY",
            "HomeTeam": "HOM",
            "HomeTeamKey": "HOM",
            "StadiumID": 9,
            "AwayTeamScore": 0,
            "HomeTeamScore": 0,
            "GlobalGameID": 0,
            "GlobalAwayTeamID": 99,
            "GlobalHomeTeamID": 98,
            "GameEndDateTime": "2000-09-22T00:10:17",
            "NeutralVenue": False,
            "AwayTeamID": 99,
            "HomeTeamID": 98,
            "SeriesInfo": None,
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
        country=key,
    )


# = Start Tests: ====


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
async def test_nfl_update_teams(mock_client: AsyncClient, mocker: MockerFixture) -> None:
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
        side_effect=[timeframe, nfl_teams_payload()],
    )

    await nfl.update_teams(client=mock_client)

    assert nfl.season == "2025REG"
    assert nfl.week == "3"
    assert set(nfl.teams.keys()) == {1, 2}  # type: ignore[unreachable]
    t1 = nfl.teams[1]
    assert t1.name == "Cardinals"
    assert get_data.call_count == 2
    assert "/Timeframes/current" in get_data.call_args_list[0].kwargs["url"]
    assert "args" not in get_data.call_args_list[0].kwargs
    assert get_data.call_args_list[0].kwargs["headers"] == nfl.api_headers()
    assert "/Teams" in get_data.call_args_list[1].kwargs["url"]
    assert "args" not in get_data.call_args_list[1].kwargs
    assert get_data.call_args_list[1].kwargs["headers"] == nfl.api_headers()


@pytest.mark.asyncio
@freezegun.freeze_time("2025-09-22T00:00:00", tz_offset=0)
async def test_nfl_superbowl(mock_client: AsyncClient, mocker: MockerFixture) -> None:
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
        side_effect=[timeframe, nfl_teams_payload()],
    )

    await nfl.get_season(client=mock_client)

    assert nfl.season == "2025POST"
    assert nfl.week == 4


@pytest.mark.asyncio
async def test_nhl_update_teams_with_None_season(
    mocker: MockerFixture, mock_client: AsyncClient
) -> None:
    """Test NHL team updates with None season."""
    nhl = NHL(settings=settings.providers.sports)
    get_data = mocker.patch(
        "merino.providers.suggest.sports.backends.sportsdata.common.sports.get_data",
        return_value={"ApiSeason": None},
    )
    await nhl.update_teams(client=mock_client)
    assert nhl.season is None
    assert nhl.teams == {}
    get_data.assert_called_once()


@pytest.mark.asyncio
async def test_nhl_update_teams(
    mock_client: AsyncClient,
    mocker: MockerFixture,
) -> None:
    """Test NHL team updates."""
    nhl = NHL(settings=settings.providers.sports)
    teams_payload = nhl_teams_payload()

    current_season = {"ApiSeason": "2026PRE"}
    get_data = mocker.patch(
        "merino.providers.suggest.sports.backends.sportsdata.common.sports.get_data",
        side_effect=[current_season, teams_payload],
    )
    await nhl.update_teams(client=mock_client)
    assert nhl.season == "2026PRE"
    assert set(nhl.teams.keys()) == {1, 2}
    assert get_data.call_count == 2


@pytest.mark.asyncio
async def test_nba_update_teams(mock_client: AsyncClient, mocker: MockerFixture) -> None:
    """Test NHL team updates."""
    nba = NBA(settings=settings.providers.sports)
    teams_payload = nba_teams_payload()
    current_season = {"ApiSeason": "2026PRE"}
    get_data = mocker.patch(
        "merino.providers.suggest.sports.backends.sportsdata.common.sports.get_data",
        side_effect=[current_season, teams_payload],
    )
    await nba.update_teams(client=mock_client)
    assert nba.season == "2026PRE"
    assert set(nba.teams.keys()) == {20000001, 20000002}
    assert get_data.call_count == 2


@pytest.mark.asyncio
async def test_mlb_get_team(mock_client: AsyncClient, mocker: MockerFixture) -> None:
    """Test MLB team getting"""
    sport = MLB(settings=settings.providers.sports)
    mock_team = MagicMock(spec=Team)
    sport.teams = {1: mock_team}
    assert await sport.get_team(1) == mock_team


@pytest.mark.asyncio
async def test_mlb_update_teams(mock_client: AsyncClient, mocker: MockerFixture) -> None:
    """Test MLB team updates."""
    sport = MLB(settings=settings.providers.sports)
    teams_payload = mlb_teams_payload()
    current_season = {"ApiSeason": "2026PRE"}
    get_data = mocker.patch(
        "merino.providers.suggest.sports.backends.sportsdata.common.sports.get_data",
        side_effect=[current_season, teams_payload],
    )
    await sport.update_teams(client=mock_client)
    assert sport.season == "2026PRE"
    assert set(sport.teams.keys()) == {1, 2}
    assert get_data.call_count == 2


@freezegun.freeze_time("2025-09-22T00:00:00", tz_offset=0)
@pytest.mark.asyncio
async def test_ucl_update_teams(mock_client: AsyncClient, mocker: MockerFixture) -> None:
    """Test ucl team updates."""
    ucl = UCL(settings=settings.providers.sports)
    teams_payload = soccer_teams_payload()
    get_data = mocker.patch(
        "merino.providers.suggest.sports.backends.sportsdata.common.sports.get_data",
        side_effect=[teams_payload],
    )
    await ucl.update_teams(client=mock_client)
    assert ucl.season == "2025"
    assert set(ucl.teams.keys()) == {90000001, 90000002}
    assert get_data.call_count == 1
    assert "/Teams/ucl" in get_data.call_args_list[0].kwargs["url"]


@freezegun.freeze_time("2025-09-22T00:00:00", tz_offset=0)
@pytest.mark.asyncio
async def test_nfl_update_events_no_week(
    mock_client: AsyncClient,
    mocker: MockerFixture,
) -> None:
    """Test NFL event updates."""
    nfl = NFL(settings=settings.providers.sports)
    teams_payload = nfl_teams_payload()
    scores_payload = nfl_scores_payload()
    nfl.load_teams_from_source(teams_payload)
    nfl.season = "Scouting"
    nfl.week = None
    nfl.event_ttl = timedelta(weeks=2)
    get_data = mocker.patch(
        "merino.providers.suggest.sports.backends.sportsdata.common.sports.get_data",
        side_effect=[scores_payload],
    )

    await nfl.update_events(client=mock_client)
    assert not get_data.called


@freezegun.freeze_time("2025-10-05T00:00:00", tz_offset=0)
@pytest.mark.asyncio
async def test_nfl_update_events(
    mock_client: AsyncClient,
    mocker: MockerFixture,
) -> None:
    """Test NFL event updates."""
    nfl = NFL(settings=settings.providers.sports)
    teams_payload = nfl_teams_payload()
    scores_payload = nfl_test_scores_payload()
    nfl.load_teams_from_source(teams_payload)
    nfl.season = "2025REG"
    nfl.week = 3
    nfl.event_ttl = timedelta(weeks=2)

    # We get the current and the next week's scores, since NFL breaks things up by weeks.
    get_data = mocker.patch(
        "merino.providers.suggest.sports.backends.sportsdata.common.sports.get_data",
        side_effect=[scores_payload, scores_payload],
    )

    await nfl.update_events(client=mock_client)
    assert 11111 in nfl.events
    assert 22222 not in nfl.events
    ev = nfl.events[11111]
    assert ev.status == GameStatus.Scheduled
    assert ev.home_team["key"] == "ATL"
    assert ev.away_team["key"] == "ARI"
    assert isinstance(json.loads(ev.model_dump_json())["expiry"], str)
    assert get_data.call_count == 2


@pytest.mark.asyncio
async def test_nfl_update_events_with_bad_date_time(
    mock_client: AsyncClient,
    mocker: MockerFixture,
) -> None:
    """Test NFL event updates."""
    nfl = NFL(settings=settings.providers.sports)
    scores_payload = nfl_test_scores_payload()
    nfl.load_teams_from_source(nfl_teams_payload())
    nfl.season = "2025REG"
    nfl.week = 3
    nfl.event_ttl = timedelta(weeks=2)
    for payload in scores_payload:
        payload["DateTimeUTC"] = 20250101
    get_data = mocker.patch(
        "merino.providers.suggest.sports.backends.sportsdata.common.sports.get_data",
        side_effect=[scores_payload, scores_payload],
    )

    await nfl.update_events(client=mock_client)
    assert len(list(nfl.events)) == 0
    assert get_data.call_count == 2


@freezegun.freeze_time("2025-10-05T00:00:00", tz_offset=0)
@pytest.mark.asyncio
async def test_nhl_update_events(
    mock_client: AsyncClient,
    mocker: MockerFixture,
) -> None:
    """Test NHL event updates."""
    teams_payload = nhl_teams_payload()
    schedules_payload = nhl_schedule_payload()
    scores_payload = nhl_score_payload()

    within = "2025-09-22T13:30:00"  # UTC
    outside = "2026-01-22T13:30:00"
    before = "2026-07-22T13:30:00"
    schedules_payload[0].update(
        {
            "Date": within,
            "Day": within,
            "DateTime": within,
            "DateTimeUTC": within,
            "Status": "Final",
        }
    )
    schedules_payload[1].update(
        {
            "Date": outside,
            "Day": outside,
            "DateTime": outside,
            "DateTimeUTC": outside,
            "Status": "Scheduled",
        }
    )
    scores_payload[0].update(
        {
            "Date": within,
            "Day": within,
            "DateTime": within,
            "DateTimeUTC": within,
            "Status": "Final",
        }
    )
    scores_payload[1].update(
        {
            "Date": outside,
            "Day": outside,
            "DateTime": outside,
            "DateTimeUTC": outside,
            "Status": "Scheduled",
        }
    )
    scores_payload[1].update(
        {
            "Date": before,
            "Day": before,
            "DateTime": before,
            "DateTimeUTC": before,
            "Status": "Final",
        }
    )

    nhl = NHL(settings=settings.providers.sports)
    nhl.load_teams_from_source(teams_payload)
    nhl.season = "2026PRE"
    nhl.event_ttl = timedelta(weeks=2)

    get_data = mocker.patch(
        "merino.providers.suggest.sports.backends.sportsdata.common.sports.get_data",
        side_effect=[schedules_payload, scores_payload, scores_payload],
    )

    await nhl.update_events(client=mock_client)
    assert 11111 in nhl.events and 0 not in nhl.events
    ev = nhl.events[11111]
    assert ev.status == GameStatus.Final
    assert ev.home_team["key"] == "BUF"
    assert ev.away_team["key"] == "BOS"
    assert 2 == get_data.call_count
    for scall in get_data.call_args_list:
        assert scall.kwargs["url"] in [
            "https://api.sportsdata.io/v3/nhl/scores/json/SchedulesBasic/2026PRE",
            "https://api.sportsdata.io/v3/nhl/scores/json/GamesByDate/2025-SEP-22",
        ]


@freezegun.freeze_time("2025-09-22T00:00:00", tz_offset=0)
@pytest.mark.asyncio
async def test_nba_update_events(
    mock_client: AsyncClient,
    mocker: MockerFixture,
) -> None:
    """Test NHL event updates."""
    nba = NBA(settings=settings.providers.sports)
    nba.load_teams_from_source(nba_teams_payload())
    nba.season = "2026PRE"
    nba.event_ttl = timedelta(weeks=2)

    schedules_payload = nba_schedule_payload()
    scores_payload = nba_score_payload()
    within = "2025-09-22T13:30:00"  # UTC
    outside = "2026-01-22T13:30:00"
    schedules_payload[0].update(
        {
            "Date": within,
            "Day": within,
            "DateTime": within,
            "DateTimeUTC": within,
            "Status": "Final",
        }
    )
    schedules_payload[1].update(
        {
            "Date": outside,
            "Day": outside,
            "DateTime": outside,
            "DateTimeUTC": outside,
            "Status": "Scheduled",
        }
    )
    scores_payload[0].update(
        {
            "Date": within,
            "Day": within,
            "DateTime": within,
            "DateTimeUTC": within,
            "Status": "Final",
        }
    )
    scores_payload[1].update(
        {
            "Date": outside,
            "Day": outside,
            "DateTime": outside,
            "DateTimeUTC": outside,
            "Status": "Scheduled",
        }
    )

    get_data = mocker.patch(
        "merino.providers.suggest.sports.backends.sportsdata.common.sports.get_data",
        side_effect=[schedules_payload, scores_payload],
    )

    await nba.update_events(client=mock_client)
    assert 20011111 in nba.events and 20022222 not in nba.events
    assert nba.events[20011111].status == GameStatus.Final
    assert 2 == get_data.call_count
    for scall in get_data.call_args_list:
        assert scall.kwargs["url"] in [
            "https://api.sportsdata.io/v3/nba/scores/json/SchedulesBasic/2026PRE",
            "https://api.sportsdata.io/v3/nba/scores/json/ScoresBasic/2025-SEP-22",
        ]


@freezegun.freeze_time("2026-05-05T12:00:00", tz_offset=0)
@pytest.mark.asyncio
async def test_nba_update_events_score_url_uses_local_game_day(
    mock_client: AsyncClient,
    mocker: MockerFixture,
) -> None:
    """ScoresBasic URL must be keyed on the league's ET game day, not UTC.

    Regression for DISCO-4164: an evening-ET game whose DateTimeUTC rolls into the
    next UTC day was being looked up under the wrong /ScoresBasic/{day} endpoint,
    so its score never landed.
    """
    nba = NBA(settings=settings.providers.sports)
    nba.load_teams_from_source(nba_teams_payload())
    nba.season = "2026POST"
    nba.event_ttl = timedelta(weeks=2)

    # 9:30pm ET on May 4, which is 01:30 UTC on May 5 — the bug case.
    game_utc = "2026-05-05T01:30:00"
    schedules_payload = nba_schedule_payload()
    schedules_payload[0].update(
        {
            "Day": "2026-05-04T00:00:00",
            "DateTime": "2026-05-04T21:30:00",
            "DateTimeUTC": game_utc,
            "Status": "Final",
        }
    )
    schedules_payload[1].update(
        {
            "Day": "2026-05-04T00:00:00",
            "DateTime": "2026-05-04T21:30:00",
            "DateTimeUTC": game_utc,
            "Status": "Scheduled",
        }
    )

    get_data = mocker.patch(
        "merino.providers.suggest.sports.backends.sportsdata.common.sports.get_data",
        side_effect=[schedules_payload, []],
    )

    await nba.update_events(client=mock_client)

    urls = [call.kwargs["url"] for call in get_data.call_args_list]
    assert "https://api.sportsdata.io/v3/nba/scores/json/ScoresBasic/2026-MAY-04" in urls
    assert "https://api.sportsdata.io/v3/nba/scores/json/ScoresBasic/2026-MAY-05" not in urls


@freezegun.freeze_time("2025-09-22T00:00:00", tz_offset=0)
@pytest.mark.asyncio
async def test_mlb_update_events(
    mock_client: AsyncClient,
    mocker: MockerFixture,
) -> None:
    """Test MLB event updates."""
    mlb = MLB(settings=settings.providers.sports)
    mlb.load_teams_from_source(mlb_teams_payload())
    mlb.season = "2026PRE"
    mlb.event_ttl = timedelta(weeks=2)

    schedules_payload = mlb_schedule_payload()
    scores_payload = mlb_score_payload()
    within = "2025-09-22T13:30:00"  # UTC
    outside = "2026-01-22T13:30:00"
    schedules_payload[0].update(
        {
            "Date": within,
            "Day": within,
            "DateTime": within,
            "DateTimeUTC": within,
            "Status": "Final",
        }
    )
    schedules_payload[1].update(
        {
            "Date": outside,
            "Day": outside,
            "DateTime": outside,
            "DateTimeUTC": outside,
            "Status": "Scheduled",
        }
    )

    scores_payload[0].update(
        {
            "Date": within,
            "Day": within,
            "DateTime": within,
            "Status": "Final",
        }
    )
    scores_payload[1].update(
        {
            "Date": outside,
            "Day": outside,
            "DateTime": outside,
            "DateTimeUTC": outside,
            "Status": "Scheduled",
        }
    )

    get_data = mocker.patch(
        "merino.providers.suggest.sports.backends.sportsdata.common.sports.get_data",
        side_effect=[schedules_payload, scores_payload],
    )

    await mlb.update_events(client=mock_client)
    assert 11111 in mlb.events and 22222 not in mlb.events
    assert mlb.events[11111].status == GameStatus.Final
    assert get_data.call_count == 2


@freezegun.freeze_time("2025-09-22T00:00:00", tz_offset=0)
@pytest.mark.asyncio
async def test_ucl_update_events(
    mock_client: AsyncClient,
    mocker: MockerFixture,
) -> None:
    """Test UCL event updates."""
    ucl = UCL(settings=settings.providers.sports)
    teams_payload = soccer_teams_payload()
    ucl.load_teams_from_source(teams_payload)
    ucl.season = "2025"  # set by update_teams normally
    ucl.event_ttl = timedelta(weeks=2)

    schedules_payload = soccer_schedule_payload()
    scores_payload = soccer_score_payload()
    within = "2025-09-22T13:30:00"  # UTC
    outside = "2026-01-22T13:30:00"
    schedules_payload[0].update(
        {
            "Date": within,
            "Day": within,
            "DateTime": within,
            "Status": "Final",
        }
    )
    schedules_payload[1].update(
        {
            "Date": outside,
            "Day": outside,
            "DateTime": outside,
            "Status": "Scheduled",
        }
    )
    scores_payload[0].update(
        {
            "Date": within,
            "Day": within,
            "DateTime": within,
            "Status": "Final",
        }
    )
    scores_payload[1].update(
        {
            "Date": outside,
            "Day": outside,
            "DateTime": outside,
            "Status": "Scheduled",
        }
    )

    get_data = mocker.patch(
        "merino.providers.suggest.sports.backends.sportsdata.common.sports.get_data",
        side_effect=[schedules_payload, scores_payload],
    )

    await ucl.update_events(client=mock_client)
    assert 90011111 in ucl.events and 90022222 not in ucl.events
    assert "/SchedulesBasic/UCL/2025" in get_data.call_args_list[0].kwargs["url"]


def test_wcs_games_by_date_ttl_from_config() -> None:
    """The live GamesByDate cache TTL is read from config and stored as a timedelta."""
    expected_sec = settings.providers.sports.sportsdata.WCS.games_by_date_ttl_sec
    sport = WCS(settings=settings.providers.sports)
    assert sport.games_by_date_ttl == timedelta(seconds=expected_sec)


@pytest.mark.asyncio
async def test_wcs_load_areas(mock_client: AsyncClient, mocker: MockerFixture) -> None:
    """Test WCS load areas (widget)"""
    sport = WCS(settings=settings.providers.sports)
    areas_payload = json.loads("""
[
  {
    "AreaId": 1,
    "CountryCode": "INT",
    "Name": "World",
    "Competitions": [
      {
        "CompetitionId": 21,
        "AreaId": 1,
        "AreaName": "World",
        "Name": "FIFA World Cup",
        "Gender": "Male",
        "Type": "International",
        "Format": "International Cup",
        "Key": "FIFA",
        "Seasons": [
          {
            "SeasonId": 50,
            "CompetitionId": 21,
            "Season": 2018,
            "Name": "2018 Russia",
            "CompetitionName": "FIFA World Cup",
            "StartDate": "2018-06-14T00:00:00",
            "EndDate": "2018-07-15T00:00:00",
            "CurrentSeason": false,
            "Rounds": [
              {
                "RoundId": 196,
                "SeasonId": 50,
                "Season": 2018,
                "SeasonType": 1,
                "Name": "Group Stage",
                "Type": "Table",
                "StartDate": "2018-06-14T00:00:00",
                "EndDate": "2018-06-28T00:00:00",
                "CurrentWeek": 3,
                "CurrentRound": false,
                "Games": [],
                "Standings": [],
                "TeamSeasons": [],
                "PlayerSeasons": []
              }
            ]
          },
          {
            "SeasonId": 56,
            "CompetitionId": 21,
            "Season": 2014,
            "Name": "2014 Brazil",
            "CompetitionName": "FIFA World Cup",
            "StartDate": "2014-06-12T00:00:00",
            "EndDate": "2014-07-13T00:00:00",
            "CurrentSeason": false,
            "Rounds": [
              {
                "RoundId": 325,
                "SeasonId": 56,
                "Season": 2014,
                "SeasonType": 1,
                "Name": "Group Stage",
                "Type": "Table",
                "StartDate": "2014-06-12T00:00:00",
                "EndDate": "2014-06-26T00:00:00",
                "CurrentWeek": 3,
                "CurrentRound": false,
                "Games": [],
                "Standings": [],
                "TeamSeasons": [],
                "PlayerSeasons": []
              }
            ]
          }
        ]
      },
      {
        "CompetitionId": 25,
        "AreaId": 1,
        "AreaName": "World",
        "Name": "FIFA Friendlies",
        "Gender": "Male",
        "Type": "International",
        "Format": "International Cup",
        "Key": "FIFAF",
        "Seasons": [
          {
            "SeasonId": 59,
            "CompetitionId": 25,
            "Season": 2018,
            "Name": "2018",
            "CompetitionName": "FIFA Friendlies",
            "StartDate": "2018-01-01T00:00:00",
            "EndDate": "2018-12-31T00:00:00",
            "CurrentSeason": false,
            "Rounds": [
              {
                "RoundId": 237,
                "SeasonId": 59,
                "Season": 2018,
                "SeasonType": 3,
                "Name": "Regular Round",
                "Type": "Cup",
                "StartDate": "2018-01-01T00:00:00",
                "EndDate": "2018-12-31T00:00:00",
                "CurrentWeek": null,
                "CurrentRound": false,
                "Games": [],
                "Standings": [],
                "TeamSeasons": [],
                "PlayerSeasons": []
              },
              {
                "RoundId": 238,
                "SeasonId": 59,
                "Season": 2018,
                "SeasonType": 3,
                "Name": "February",
                "Type": "Cup",
                "StartDate": "2018-02-01T00:00:00",
                "EndDate": "2018-02-28T00:00:00",
                "CurrentWeek": null,
                "CurrentRound": false,
                "Games": [],
                "Standings": [],
                "TeamSeasons": [],
                "PlayerSeasons": []
              }
            ]
          }
        ]
      }
    ]
  },
  {
    "AreaId": 2,
    "CountryCode": "ASI",
    "Name": "Asia",
    "Competitions": [
    ]
  },
  {
    "AreaId": 196,
    "CountryCode": "TUR",
    "Name": "Türkiye",
    "Competitions": []
  }
]
""")
    _get_data = mocker.patch(
        "merino.providers.suggest.sports.backends.sportsdata.common.sports.get_data",
        side_effect=[areas_payload],
    )
    mock_cache = MagicMock(spec=RedisAdapter)
    mock_cache.hset.return_value = 1
    sport.cache = mock_cache
    await sport.load_areas(areas_payload)
    assert mock_cache.hset.call_args_list == [
        call("sport:wcs:v1:area:1", {"name": "World", "code": "INT"}),
        call("sport:wcs:v1:area:2", {"name": "Asia", "code": "ASI"}),
        call(
            "sport:wcs:v1:area:196",
            {"name": "Türkiye", "code": "TUR", "aliases": "turkey"},
        ),
    ]


def wcs_competitions_payload() -> list[dict]:
    """Return a trimmed SportsData Competitions response with relevant (World Cup) and irrelevant
    competition and seasons.
    """
    return [
        {
            "Key": "FIFA",
            "Seasons": [
                {
                    "Season": 2026,
                    "Rounds": [
                        {"RoundId": 1615, "Name": "Group Stage"},
                        {"RoundId": 1616, "Name": "Round of 32"},
                    ],
                },
                {
                    "Season": 2018,
                    "Rounds": [{"RoundId": 196, "Name": "Group Stage"}],
                },
            ],
        },
        {
            "Key": "FAFFY",
            "Seasons": [
                {
                    "Season": 2026,
                    "Rounds": [{"RoundId": 999, "Name": "Sudden Death"}],
                }
            ],
        },
    ]


@freezegun.freeze_time("2026-06-10T00:00:00", tz_offset=0)
@pytest.mark.asyncio
async def test_wcs_load_rounds(mock_client: AsyncClient, mocker: MockerFixture) -> None:
    """load_rounds populates self.rounds and caches it for the current world cup."""
    sport = WCS(settings=settings.providers.sports)
    competitions = wcs_competitions_payload()
    mocker.patch(
        "merino.providers.suggest.sports.backends.sportsdata.common.sports.get_data",
        side_effect=[competitions],
    )
    mock_cache = MagicMock(spec=RedisAdapter)
    sport.cache = mock_cache

    await sport.load_rounds(mock_client)

    assert sport.rounds == {1615: "Group Stage", 1616: "Round of 32"}
    mock_cache.set.assert_called_once_with(
        "sport:wcs:v1:rounds",
        orjson.dumps({1615: "Group Stage", 1616: "Round of 32"}, option=orjson.OPT_NON_STR_KEYS),
    )


@freezegun.freeze_time("2026-06-10T00:00:00", tz_offset=0)
@pytest.mark.asyncio
async def test_wcs_load_areas_records_last_synced_at(
    mock_client: AsyncClient, mocker: MockerFixture
) -> None:
    """load_areas sets the last_synced_at gauge for the areas component on success."""
    sport = WCS(settings=settings.providers.sports)
    mocker.patch(
        "merino.providers.suggest.sports.backends.sportsdata.common.sports.get_data",
        side_effect=[[]],
    )
    sport.cache = MagicMock(spec=RedisAdapter)
    gauge = mocker.patch(
        "merino.providers.suggest.sports.backends.sportsdata.common.sports.last_synced_at"
    )

    await sport.load_areas(mock_client)

    gauge.set.assert_called_once_with(
        datetime.now().timestamp(),
        {"component": "areas", "sport": "WCS"},
    )


@freezegun.freeze_time("2026-06-10T00:00:00", tz_offset=0)
@pytest.mark.asyncio
async def test_wcs_load_rounds_records_last_synced_at(
    mock_client: AsyncClient, mocker: MockerFixture
) -> None:
    """load_rounds sets the last_synced_at gauge for the rounds component on success."""
    sport = WCS(settings=settings.providers.sports)
    mocker.patch(
        "merino.providers.suggest.sports.backends.sportsdata.common.sports.get_data",
        side_effect=[wcs_competitions_payload()],
    )
    sport.cache = MagicMock(spec=RedisAdapter)
    gauge = mocker.patch(
        "merino.providers.suggest.sports.backends.sportsdata.common.sports.last_synced_at"
    )

    await sport.load_rounds(mock_client)

    gauge.set.assert_called_once_with(
        datetime.now().timestamp(),
        {"component": "rounds", "sport": "WCS"},
    )


@freezegun.freeze_time("2025-09-22T00:00:00", tz_offset=0)
@pytest.mark.asyncio
async def test_wcs_update_teams_records_last_synced_at(
    mock_client: AsyncClient, mocker: MockerFixture
) -> None:
    """update_teams sets the last_synced_at gauge for the teams component on success."""
    sport = WCS(settings=settings.providers.sports)
    mocker.patch(
        "merino.providers.suggest.sports.backends.sportsdata.common.sports.get_data",
        side_effect=[wcs_teams_payload()],
    )
    gauge = mocker.patch(
        "merino.providers.suggest.sports.backends.sportsdata.common.sports.last_synced_at"
    )

    await sport.update_teams(mock_client)

    gauge.set.assert_called_once_with(
        datetime.now().timestamp(),
        {"component": "teams", "sport": "WCS"},
    )


@freezegun.freeze_time("2025-09-22T00:00:00", tz_offset=0)
@pytest.mark.asyncio
async def test_wcs_update_events_records_last_synced_at(
    mock_client: AsyncClient, mocker: MockerFixture
) -> None:
    """update_events sets the last_synced_at gauge for the events component on success."""
    sport = WCS(settings=settings.providers.sports)
    await sport.async_load_teams_from_source(wcs_teams_payload())
    sport.season = "2025"
    sport.event_ttl = timedelta(weeks=2)
    sport.rounds = {1615: "Group Stage"}
    mocker.patch(
        "merino.providers.suggest.sports.backends.sportsdata.common.sports.get_data",
        side_effect=[wcs_schedule_payload(), wcs_score_payload()],
    )
    mocker.patch.object(sport, "cache_events", new=mocker.AsyncMock())
    gauge = mocker.patch(
        "merino.providers.suggest.sports.backends.sportsdata.common.sports.last_synced_at"
    )

    await sport.update_events(client=mock_client)

    gauge.set.assert_called_once_with(
        datetime.now().timestamp(),
        {"component": "events", "sport": "WCS"},
    )


def test_wcs_event_details_includes_stage_from_rounds() -> None:
    """event_details resolves the schedule's RoundId to a stage name via self.rounds."""
    sport = WCS(settings=settings.providers.sports)
    sport.rounds = {1615: "Group Stage", 1616: "Round of 32"}

    details = sport.event_details({"RoundId": 1616, "Period": "Regular"})

    assert details["stage"] == "Round of 32"


def test_wcs_event_details_unknown_round_id_returns_none_stage() -> None:
    """A RoundId not in the cached mapping resolves to stage=None."""
    sport = WCS(settings=settings.providers.sports)
    sport.rounds = {1615: "Group Stage"}

    details = sport.event_details({"RoundId": 9999})

    assert details["stage"] is None


def test_wcs_event_details_missing_round_id_returns_none_stage() -> None:
    """Schedule rows without a RoundId resolve to stage=None."""
    sport = WCS(settings=settings.providers.sports)
    sport.rounds = {1615: "Group Stage"}

    details = sport.event_details({})

    assert details["stage"] is None


def test_wcs_event_details_no_rounds_returns_none_stage() -> None:
    """If rounds can't be loaded or aren't found (default to empty dict)
    stage returns none.
    """
    sport = WCS(settings=settings.providers.sports)
    sport.rounds = {}

    details = sport.event_details({})

    assert details["stage"] is None


@pytest.mark.parametrize(
    ("clock", "period", "status", "expected"),
    [
        pytest.param("90+3", "PenaltyShootout", GameStatus.InProgress, "PEN", id="live-penalty"),
        pytest.param(None, "PenaltyShootout", GameStatus.InProgress, "PEN", id="live-no-clock"),
        pytest.param("90+3", "PenaltyShootout", GameStatus.F_SO, "90+3", id="completed-shootout"),
        pytest.param("90+3", "PenaltyShootout", GameStatus.Scheduled, "90+3", id="not-yet-live"),
        pytest.param("45", "Regular", GameStatus.InProgress, "45", id="non-penalty"),
        pytest.param(90, "ExtraTime", GameStatus.InProgress, "90", id="non-str-clock-coerced"),
        pytest.param(None, "Regular", GameStatus.InProgress, None, id="no-clock"),
    ],
)
def test_wcs_clock_or_penalty_hint(
    clock: Any, period: Any, status: GameStatus, expected: str | None
) -> None:
    """Surface PEN only for a live penalty shootout; otherwise pass the clock through."""
    assert WCS._clock_or_penalty_hint(clock, period, status) == expected


@pytest.mark.parametrize(
    ("row", "expected_clock"),
    [
        pytest.param(
            {"Period": "PenaltyShootout", "Status": "InProgress", "ClockDisplay": "90+3"},
            "PEN",
            id="live-shootout-gets-pen",
        ),
        pytest.param(
            {"Period": "PenaltyShootout", "Status": "Final", "ClockDisplay": "90+3"},
            "90+3",
            id="completed-shootout-keeps-clock",
        ),
        pytest.param(
            # Missing Status normalizes to a non-live status, so no PEN hint.
            {"Period": "PenaltyShootout", "ClockDisplay": "90+3"},
            "90+3",
            id="missing-status-keeps-clock",
        ),
        pytest.param(
            {"Period": "Regular", "Status": "InProgress", "ClockDisplay": "45"},
            "45",
            id="non-penalty-keeps-clock",
        ),
    ],
)
def test_wcs_event_details_clock(row: dict[str, Any], expected_clock: str | None) -> None:
    """event_details wires Status/Period/clock into the penalty-shootout hint.

    Both `/matches` and `/live` reach this through `event_from_row` and
    `apply_score_update`, so covering the chokepoint covers both endpoints.
    """
    sport = WCS(settings=settings.providers.sports)

    assert sport.event_details(row)["clock"] == expected_clock


@freezegun.freeze_time("2026-06-10T00:00:00", tz_offset=0)
@pytest.mark.asyncio
async def test_wcs_update_events_loads_rounds_when_empty(
    mock_client: AsyncClient, mocker: MockerFixture
) -> None:
    """Ensure that lazily loaded rounds are fetched if they aren't
    already loaded during update_events
    """
    sport = WCS(settings=settings.providers.sports)
    await sport.async_load_teams_from_source(wcs_teams_payload())
    sport.event_ttl = timedelta(weeks=8)

    competitions = wcs_competitions_payload()
    mocker.patch(
        "merino.providers.suggest.sports.backends.sportsdata.common.sports.get_data",
        side_effect=[competitions, wcs_schedule_payload(), wcs_score_payload()],
    )
    mock_cache = MagicMock(spec=RedisAdapter)
    sport.cache = mock_cache

    await sport.update_events(client=mock_client)

    assert sport.rounds == {1615: "Group Stage", 1616: "Round of 32"}
    assert sport.events[90011111].stage == "Group Stage"


@freezegun.freeze_time("2025-09-22T00:00:00", tz_offset=0)
@pytest.mark.asyncio
async def test_wcs_update_events(
    mock_client: AsyncClient,
    mocker: MockerFixture,
) -> None:
    """Test WCS event updates."""
    sport = WCS(settings=settings.providers.sports)
    teams_payload = wcs_teams_payload()
    await sport.async_load_teams_from_source(teams_payload)
    sport.season = "2025"  # set by update_teams normally
    sport.event_ttl = timedelta(weeks=2)
    # Preload rounds to avoid mocking external call
    sport.rounds = {1615: "Group Stage"}

    schedules_payload = wcs_schedule_payload()
    scores_payload = wcs_score_payload()
    within = "2025-09-22T13:30:00"  # UTC
    outside = "2026-01-22T13:30:00"
    schedules_payload[0].update(
        {
            "Date": within,
            "Day": within,
            "DateTime": within,
            "Status": "Final",
        }
    )
    schedules_payload[1].update(
        {
            "Date": outside,
            "Day": outside,
            "DateTime": outside,
            "Status": "Scheduled",
        }
    )
    scores_payload[0].update(
        {
            "Date": within,
            "Day": within,
            "DateTime": within,
            "Status": "Final",
            "Period": "PenaltyShootout",
            "ClockDisplay": "120",
            "HomeTeamScorePenalty": 5,
            "AwayTeamScorePenalty": 4,
        }
    )
    scores_payload[1].update(
        {
            "Date": outside,
            "Day": outside,
            "DateTime": outside,
            "Status": "Scheduled",
        }
    )

    get_data = mocker.patch(
        "merino.providers.suggest.sports.backends.sportsdata.common.sports.get_data",
        side_effect=[schedules_payload, scores_payload],
    )

    global_offset = 90000000
    await sport.update_events(client=mock_client)
    event = sport.events[global_offset + 11111]
    assert global_offset + 11111 in sport.events and global_offset + 22222 not in sport.events
    assert event.status == GameStatus.Final
    assert event.period == "PenaltyShootout"
    assert event.clock == "120"
    assert event.home_penalty == 5
    assert event.away_penalty == 4
    assert event.round_id == 1708
    assert event.season_type == 3
    assert event.group == "Group A"
    assert event.winner == "HomeTeam"
    assert event.is_closed is True
    assert 2 == get_data.call_count
    for scall in get_data.call_args_list:
        assert scall.kwargs["url"] in [
            "https://api.sportsdata.io/v4/soccer/scores/json/SchedulesBasic/fifa/2025",
            "https://api.sportsdata.io/v4/soccer/scores/json/GamesByDate/fifa/2025-SEP-22",
        ]


@pytest.mark.parametrize(
    (
        "schedule_overrides",
        "score_overrides",
        "expected_games_by_date_url",
        "expected_status",
    ),
    [
        pytest.param(
            {},
            {
                "Status": "InProgress",
                "Period": "1",
                "ClockDisplay": "16",
                "HomeTeamScore": 1,
                "AwayTeamScore": 0,
                "UpdatedUtc": "2026-06-11T19:16:00",
            },
            "https://api.sportsdata.io/v4/soccer/scores/json/GamesByDate/fifa/2026-JUN-11",
            GameStatus.InProgress,
            id="scheduled-active-window",
        ),
        pytest.param(
            {
                "DateTime": "2026-06-20T19:00:00",
                "Day": "2026-06-20T00:00:00",
                "Status": "Final",
                "HomeTeamScore": 2,
                "AwayTeamScore": 1,
                "UpdatedUtc": "2026-06-20T21:00:00",
            },
            {},
            "https://api.sportsdata.io/v4/soccer/scores/json/GamesByDate/fifa/2026-JUN-20",
            GameStatus.Final,
            id="non-scheduled-outside-active-window",
        ),
    ],
)
@freezegun.freeze_time("2026-06-11T12:00:00", tz_offset=0)
@pytest.mark.asyncio
async def test_wcs_update_events_fetches_games_by_date_for_live_relevant_days(
    mock_client: AsyncClient,
    mocker: MockerFixture,
    schedule_overrides: dict[str, Any],
    score_overrides: dict[str, Any],
    expected_games_by_date_url: str,
    expected_status: GameStatus,
) -> None:
    """Refresh active-window days and any day already reported non-scheduled."""
    sport = WCS(settings=settings.providers.sports)
    await sport.async_load_teams_from_source(wcs_teams_payload())
    sport.event_ttl = timedelta(weeks=8)
    sport.rounds = {1615: "Group Stage"}

    schedule_row = {**wcs_schedule_payload()[0], **schedule_overrides}
    schedules_payload = [schedule_row]
    scores_payload = [{**schedule_row, **score_overrides}]
    get_data = mocker.patch(
        "merino.providers.suggest.sports.backends.sportsdata.common.sports.get_data",
        side_effect=[schedules_payload, scores_payload],
    )

    await sport.update_events(client=mock_client)

    event = sport.events[90011111]
    assert event.status == expected_status
    assert [call.kwargs["url"] for call in get_data.call_args_list] == [
        "https://api.sportsdata.io/v4/soccer/scores/json/SchedulesBasic/fifa/2026",
        expected_games_by_date_url,
    ]
    assert get_data.call_args_list[1].kwargs["ttl"] == timedelta(seconds=5)

    if expected_status == GameStatus.InProgress:
        assert event.period == "1"
        assert event.clock == "16"
        assert event.home_score == 1
        assert event.away_score == 0


@pytest.mark.asyncio
async def test_wcs_update_events_keeps_existing_events_when_schedule_fetch_fails(
    mock_client: AsyncClient,
    mocker: MockerFixture,
) -> None:
    """Schedule fetch failures should not prune existing WCS cache data."""
    sport = WCS(settings=settings.providers.sports)
    sport.rounds = {1615: "Group Stage"}
    existing_events = {123: mocker.Mock(spec=Event)}
    sport.events = existing_events
    cache_events = mocker.patch.object(sport, "cache_events", new=mocker.AsyncMock())
    get_data = mocker.patch(
        "merino.providers.suggest.sports.backends.sportsdata.common.sports.get_data",
        side_effect=SportsDataError("provider down"),
    )

    await sport.update_events(client=mock_client)

    assert sport.events == existing_events
    get_data.assert_called_once()
    cache_events.assert_not_awaited()


@freezegun.freeze_time("2026-06-11T12:00:00", tz_offset=0)
@pytest.mark.asyncio
async def test_wcs_update_events_caches_schedule_when_score_fetch_fails(
    mock_client: AsyncClient,
    mocker: MockerFixture,
) -> None:
    """Detailed score fetch failures should still cache the schedule refresh."""
    sport = WCS(settings=settings.providers.sports)
    await sport.async_load_teams_from_source(wcs_teams_payload())
    sport.event_ttl = timedelta(weeks=8)
    sport.rounds = {1615: "Group Stage"}
    cache_events = mocker.patch.object(sport, "cache_events", new=mocker.AsyncMock())
    get_data = mocker.patch(
        "merino.providers.suggest.sports.backends.sportsdata.common.sports.get_data",
        side_effect=[[wcs_schedule_payload()[0]], SportsDataError("provider down")],
    )

    await sport.update_events(client=mock_client)

    assert 90011111 in sport.events
    assert get_data.call_count == 2
    cache_events.assert_awaited_once()


@pytest.mark.asyncio
async def test_wcs_national_teams_use_country_name_for_event_display() -> None:
    """WCS team full names are federation names, not widget display names."""
    sport = WCS(settings=settings.providers.sports)

    await sport.async_load_teams_from_source(wcs_teams_payload())

    team = sport.teams[90000001]
    assert team.name == "England"
    assert team.fullname == "England"
    assert "The Football Association" in team.aliases
    assert team.minimal()["name"] == "England"


@pytest.mark.asyncio
async def test_wcs_national_teams_include_alias_name_for_event_display() -> None:
    """WCS team full names are federation names, not widget display names."""
    sport = WCS(settings=settings.providers.sports)
    mock_cache = MagicMock(spec=RedisAdapter)
    # return an area record without the alias set to replicate older cached data.
    mock_cache.hgetall.return_value = {b"name": "Türkiye".encode(), b"code": b"TUR"}
    sport.cache = mock_cache
    source = wcs_teams_payload()
    source[0]["Key"] = "TUR"
    source[0]["Name"] = "Türkiye"

    await sport.async_load_teams_from_source(source)

    team = sport.teams[90000001]
    assert team.name == "Türkiye"
    assert "turkey" in team.terms


@pytest.mark.asyncio
async def test_wcs_curacao_alias_added_despite_area_pointing_at_korea() -> None:
    """SportsData ships Curaçao with Key=KOR and Korea's AreaId.

    _TEAM_KEY_OVERRIDES remaps the team key to CUW, but the area-based alias
    lookup sees code=KOR (no alias). Verify the team.key fallback still
    appends 'curacao' to the search terms and corrects team.country.
    """
    sport = WCS(settings=settings.providers.sports)
    mock_cache = MagicMock(spec=RedisAdapter)
    mock_cache.hgetall.return_value = {b"name": b"Korea Republic", b"code": b"KOR"}
    sport.cache = mock_cache
    source = wcs_teams_payload()
    source[0]["Key"] = "KOR"
    source[0]["Name"] = "Curaçao"

    await sport.async_load_teams_from_source(source)

    team = sport.teams[90000001]
    assert team.key == "CUW"
    assert team.country == "CUW"
    assert "curacao" in team.terms


@freezegun.freeze_time("2026-06-10T00:00:00", tz_offset=0)
@pytest.mark.asyncio
async def test_wcs_sportsdata_schedule_and_games_by_date_payloads_match_expected_shape() -> None:
    """Validate captured FIFA payloads from /SchedulesBasic and /GamesByDate.

    Drives the WCS load path with real SportsData rows so subtle key-name drift
    (e.g. `GlobalGameId` vs `GlobalGameID`) surfaces here rather than in prod.
    """
    sport = WCS(settings=settings.providers.sports)
    sport.event_ttl = timedelta(weeks=8)
    sport.rounds = {1615: "Group Stage", 1616: "Round of 32"}
    await sport.async_load_teams_from_source(wcs_static_teams_payload({"SWE", "TUN"}))

    sport.load_schedules_from_source(wcs_static_schedule_payload(), event_timezone=ZoneInfo("UTC"))

    # SWE vs TUN has both teams loaded. The knockout placeholder is also
    # retained with TBD teams, while rows whose real teams are missing from the
    # test team cache (e.g. SWE vs NLD) are still dropped.
    assert set(sport.events) == {90086918, 90086979}
    event = sport.events[90086918]
    assert event.away_team["key"] == "TUN"
    assert event.away_team["name"] == "Tunisia"
    assert event.home_team["key"] == "SWE"
    assert event.home_team["name"] == "Sweden"
    assert event.date == datetime(2026, 6, 15, 2, 0, tzinfo=timezone.utc)
    assert event.period is None
    assert event.round_id == 1615
    assert event.season_type == 1
    assert event.group == "Group F"
    assert event.is_closed is False
    assert event.stage == "Group Stage"

    placeholder = sport.events[90086979]
    assert placeholder.home_team == {"key": "TBD", "name": "TBD", "colors": [], "id": 0}
    assert placeholder.away_team == {"key": "TBD", "name": "TBD", "colors": [], "id": 0}
    assert placeholder.date == datetime(2026, 6, 28, 19, 0, tzinfo=timezone.utc)
    assert placeholder.round_id == 1616
    assert placeholder.season_type == 3
    assert placeholder.group is None
    assert placeholder.stage == "Round of 32"

    sport.load_scores_from_source(
        wcs_static_games_by_date_payload(), event_timezone=ZoneInfo("UTC")
    )

    event = sport.events[90086918]
    assert event.status == GameStatus.Scheduled
    assert event.period == "Regular"
    assert event.clock is None
    assert event.home_score is None
    assert event.away_score is None
    assert event.round_id == 1615
    assert event.season_type == 1
    assert event.group == "Group F"
    assert event.winner is None
    assert event.is_closed is False
    assert event.updated == datetime(2026, 4, 29, 14, 26, 26, tzinfo=timezone.utc)


@freezegun.freeze_time("2026-06-10T00:00:00", tz_offset=0)
@pytest.mark.asyncio
async def test_wcs_ingests_knockout_placeholder_with_one_known_team() -> None:
    """A knockout row with one unassigned side keeps the known team and emits TBD."""
    sport = WCS(settings=settings.providers.sports)
    sport.event_ttl = timedelta(weeks=8)
    sport.rounds = {1617: "Quarterfinals"}
    await sport.async_load_teams_from_source(wcs_static_teams_payload({"SWE"}))

    sport.load_schedules_from_source(
        [
            {
                "GameId": 86997,
                "RoundId": 1617,
                "Season": 2026,
                "SeasonType": 3,
                "Group": None,
                "AwayTeamId": None,
                "HomeTeamId": 959,
                "Day": "2026-07-05T00:00:00",
                "DateTime": "2026-07-05T20:00:00",
                "Status": "Scheduled",
                "Period": "Regular",
                "Clock": None,
                "Winner": None,
                "AwayTeamKey": None,
                "AwayTeamName": None,
                "AwayTeamScore": None,
                "HomeTeamKey": "SWE",
                "HomeTeamName": "Sweden",
                "HomeTeamScore": None,
                "Updated": "2025-12-06T20:35:30",
                "UpdatedUtc": "2025-12-07T01:35:30",
                "GlobalGameId": 90086997,
                "GlobalAwayTeamId": None,
                "GlobalHomeTeamId": 90000001,
                "IsClosed": False,
            }
        ],
        event_timezone=ZoneInfo("UTC"),
    )

    event = sport.events[90086997]
    assert event.home_team["key"] == "SWE"
    assert event.home_team["name"] == "Sweden"
    assert event.away_team == {"key": "TBD", "name": "TBD", "colors": [], "id": 0}
    assert event.stage == "Quarterfinals"


@freezegun.freeze_time("2025-09-22T00:00:00", tz_offset=0)
@pytest.mark.asyncio
async def test_wcs_update_teams(mock_client: AsyncClient, mocker: MockerFixture) -> None:
    """Test WCS team updates."""
    sport = WCS(settings=settings.providers.sports)
    teams_payload = wcs_teams_payload()
    get_data = mocker.patch(
        "merino.providers.suggest.sports.backends.sportsdata.common.sports.get_data",
        side_effect=[teams_payload],  # called twice per code
    )
    await sport.update_teams(client=mock_client)
    assert sport.season == "2025"
    assert set(sport.teams.keys()) == {90000001, 90000002}
    assert get_data.call_count == 1

    assert "/Teams/fifa" in get_data.call_args_list[0].kwargs["url"]


# WCS Widget tests ===


@pytest.mark.asyncio
async def test_wcs_get_team(mock_client: AsyncClient, mocker: MockerFixture) -> None:
    """Test WCS team getting"""
    sport = WCS(settings=settings.providers.sports)
    mock_team = MagicMock(spec=Team)

    sport.teams = {1: mock_team}

    assert await sport.get_team(1) == mock_team


@pytest.mark.asyncio
async def test_team_cache_restore(mock_client: AsyncClient) -> None:
    """Test team caching and restoration"""
    sport = WCS(settings=settings.providers.sports)
    teams = {
        1: Team(
            terms="",
            fullname="Home Team",
            name="Home",
            key="HOM",
            id=1,
            aliases=["Home"],
            colors=["white"],
            updated=datetime.now(),
            expiry=datetime.now() + timedelta(seconds=10),
            locale=None,
            country="ENG",
        ),
        2: Team(
            terms="",
            fullname="Away Team",
            name="Away",
            key="AWY",
            id=2,
            aliases=["Away"],
            colors=["black"],
            updated=datetime.now(),
            expiry=datetime.now() + timedelta(seconds=10),
            locale=None,
            country="FRA",
        ),
    }
    sport.teams = teams
    mock_cache = MagicMock(spec=RedisAdapter)
    mock_cache.get.side_effect = [None, b'["sport:wcs:v1:team:1", "sport:wcs:v1:team:2"]']
    mock_cache.mget.return_value = [
        b'{"terms": "", "fullname": "Home Team", "name": "Home", "key": "HOM", "id": 1, "locale": null, "aliases": ["Home"], "colors": ["white"], "updated": 1777935457.922995, "expiry": 1777935467.922997, "country": "ENG"}',
        b'{"terms": "", "fullname": "Away Team", "name": "Away", "key": "AWY", "id": 2, "locale": null, "aliases": ["Away"], "colors": ["black"], "updated": 1777935457.923011, "expiry": 1777935467.923011, "country": "FRA"}',
    ]

    sport.cache = mock_cache
    # for each add and the meta include.
    await sport.cache_teams()
    assert mock_cache.set.call_count == 4
    result = await sport.get_all_teams(mock_client)
    assert result[1].country == "ENG"
    assert result[2].country == "FRA"

    ss = sport.team_minimal(teams[1])
    assert ss.get("name") == "Home"


@pytest.mark.asyncio
async def test_wcs_cache_teams_accepts_cached_refresh_timestamp() -> None:
    """A cached refresh timestamp is compared as a timezone-aware datetime."""
    sport = WCS(settings=settings.providers.sports)
    now = datetime.now(tz=timezone.utc)
    sport.teams = {
        1: Team(
            terms="",
            fullname="Home",
            name="Home",
            key="HOM",
            id=1,
            aliases=["Home"],
            colors=["white"],
            updated=now,
            expiry=now + timedelta(seconds=10),
            locale=None,
            country="ENG",
        ),
    }
    mock_cache = MagicMock(spec=RedisAdapter)
    mock_cache.get.return_value = int((now - timedelta(hours=13)).timestamp()).to_bytes(8)
    sport.cache = mock_cache

    await sport.cache_teams()

    mock_cache.setnx.assert_called_once()


@pytest.mark.asyncio
async def test_team_cache_restore_skips_missing_and_invalid_entries() -> None:
    """A partial or corrupt team cache does not fail the whole WCS teams response."""
    sport = WCS(settings=settings.providers.sports)
    now = datetime.now(tz=timezone.utc)
    team = Team(
        terms="",
        fullname="Home",
        name="Home",
        key="HOM",
        id=1,
        aliases=["Home"],
        colors=["white"],
        updated=now,
        expiry=now + timedelta(seconds=10),
        locale=None,
        country="ENG",
    )
    mock_cache = MagicMock(spec=RedisAdapter)
    mock_cache.get.return_value = b'["sport:wcs:v1:team:1", "sport:wcs:v1:team:2", "bad"]'
    mock_cache.mget.return_value = [
        sport.team_as_str(team).encode(),
        None,
        b"{bad-json",
    ]
    sport.cache = mock_cache

    result = await sport.get_all_teams()

    assert list(result) == [1]
    assert result[1].country == "ENG"


@pytest.mark.asyncio
async def test_wcs_cache_events() -> None:
    """Test WCS event caching writes event JSON, calendar entries, and eliminated metadata."""
    sport = WCS(settings=settings.providers.sports)
    now = datetime(2026, 6, 15, 12, tzinfo=timezone.utc)
    event = Event(
        sport="fifa",
        id=123,
        terms="home away",
        date=now,
        original_date=now.isoformat(),
        home_team={"key": "HOM", "id": 1, "name": "Home", "colors": []},
        away_team={"key": "AWY", "id": 2, "name": "Away", "colors": []},
        home_score=2,
        away_score=1,
        status=GameStatus.Final,
        expiry=now + timedelta(days=90),
        updated=now,
        period="Regular",
        clock="90",
        round_id=1617,
        season_type=3,
        winner="HomeTeam",
        is_closed=True,
    )
    sport.events = {event.id: event}
    mock_cache = MagicMock(spec=RedisAdapter)
    mock_cache.zrange.return_value = []
    sport.cache = mock_cache

    await sport.cache_events()

    mock_cache.set.assert_any_call(
        "sport:wcs:v1:event:123",
        sport.event_as_serialized(event),
        ttl=sport.event_ttl,
    )
    mock_cache.set.assert_any_call(
        eliminated_team_keys_cache_key(sport.cache_prefix),
        b'["AWY"]',
    )
    mock_cache.zadd.assert_called_once_with(
        "sport:wcs:v1:calendar",
        {"sport:wcs:v1:event:123": int(now.timestamp())},
    )


@pytest.mark.asyncio
async def test_wcs_cache_events_does_not_replace_eliminated_metadata_on_empty_refresh() -> None:
    """An empty non-authoritative refresh leaves cached eliminated-team metadata alone."""
    sport = WCS(settings=settings.providers.sports)
    mock_cache = MagicMock(spec=RedisAdapter)
    mock_cache.zrange.return_value = [b"sport:wcs:v1:event:999"]
    sport.cache = mock_cache

    await sport.cache_events()

    mock_cache.set.assert_not_called()


@pytest.mark.asyncio
async def test_wcs_get_eliminated_team_keys_from_cache() -> None:
    """WCS eliminated team metadata is restored from one Redis key."""
    sport = WCS(settings=settings.providers.sports)
    mock_cache = MagicMock(spec=RedisAdapter)
    mock_cache.get.return_value = b'["AWY","HOM"]'
    sport.cache = mock_cache

    result = await sport.get_eliminated_team_keys()

    assert result == {"AWY", "HOM"}
    mock_cache.get.assert_called_once_with(eliminated_team_keys_cache_key(sport.cache_prefix))


@pytest.mark.asyncio
async def test_wcs_get_eliminated_team_keys_bad_cache_fails_open() -> None:
    """Malformed eliminated-team metadata does not fail the teams endpoint."""
    sport = WCS(settings=settings.providers.sports)
    mock_cache = MagicMock(spec=RedisAdapter)
    mock_cache.get.return_value = b"{bad-json"
    sport.cache = mock_cache

    assert await sport.get_eliminated_team_keys() == set()


@pytest.mark.asyncio
async def test_wcs_cache_events_updates_calendar_when_event_moves_earlier() -> None:
    """WCS event calendar scores are updated even when SportsData moves kickoff earlier."""
    sport = WCS(settings=settings.providers.sports)
    original = datetime(2026, 6, 15, 12, tzinfo=timezone.utc)
    moved_earlier = original - timedelta(hours=2)
    event = Event(
        sport="fifa",
        id=123,
        terms="home away",
        date=original,
        original_date=original.isoformat(),
        home_team={"key": "HOM", "id": 1, "name": "Home", "colors": []},
        away_team={"key": "AWY", "id": 2, "name": "Away", "colors": []},
        home_score=2,
        away_score=1,
        status=GameStatus.Scheduled,
        expiry=original + timedelta(days=90),
        updated=original,
    )
    sport.events = {event.id: event}
    mock_cache = MagicMock(spec=RedisAdapter)
    mock_cache.zrange.return_value = []
    sport.cache = mock_cache

    await sport.cache_events()
    event.date = moved_earlier
    await sport.cache_events()

    assert mock_cache.zadd.call_args_list[0].args == (
        "sport:wcs:v1:calendar",
        {"sport:wcs:v1:event:123": int(original.timestamp())},
    )
    assert mock_cache.zadd.call_args_list[1].args == (
        "sport:wcs:v1:calendar",
        {"sport:wcs:v1:event:123": int(moved_earlier.timestamp())},
    )
    assert all("gt" not in call.kwargs for call in mock_cache.zadd.call_args_list)


@pytest.mark.asyncio
async def test_wcs_cache_events_prunes_removed_events_from_calendar() -> None:
    """WCS cache refresh removes events that are no longer present in source data."""
    sport = WCS(settings=settings.providers.sports)
    now = datetime(2026, 6, 15, 12, tzinfo=timezone.utc)
    event = Event(
        sport="fifa",
        id=123,
        terms="home away",
        date=now,
        original_date=now.isoformat(),
        home_team={"key": "HOM", "id": 1, "name": "Home", "colors": []},
        away_team={"key": "AWY", "id": 2, "name": "Away", "colors": []},
        home_score=2,
        away_score=1,
        status=GameStatus.Scheduled,
        expiry=now + timedelta(days=90),
        updated=now,
    )
    sport.events = {event.id: event}
    mock_cache = MagicMock(spec=RedisAdapter)
    mock_cache.zrange.return_value = [
        b"sport:wcs:v1:event:123",
        b"sport:wcs:v1:event:999",
        b"sport:wcs:v1:event:888",
    ]
    sport.cache = mock_cache

    await sport.cache_events()

    mock_cache.zrange.assert_called_once_with(
        "sport:wcs:v1:calendar",
        min=0,
        max=-1,
        byScore=False,
    )
    mock_cache.delete.assert_called_once_with("sport:wcs:v1:event:999", "sport:wcs:v1:event:888")
    mock_cache.zrem.assert_called_once_with(
        "sport:wcs:v1:calendar",
        "sport:wcs:v1:event:999",
        "sport:wcs:v1:event:888",
    )


@pytest.mark.asyncio
async def test_wcs_cache_events_refuses_to_prune_from_empty_refresh() -> None:
    """WCS cache refresh does not wipe the calendar from an empty active event set."""
    sport = WCS(settings=settings.providers.sports)
    mock_cache = MagicMock(spec=RedisAdapter)
    mock_cache.zrange.return_value = [b"sport:wcs:v1:event:999"]
    sport.cache = mock_cache

    await sport.cache_events()

    mock_cache.delete.assert_not_called()
    mock_cache.zrem.assert_not_called()


@freezegun.freeze_time("2026-06-10T00:00:00", tz_offset=0)
@pytest.mark.asyncio
async def test_wcs_update_events_prunes_previously_cached_events_removed_from_source(
    mock_client: AsyncClient,
    mocker: MockerFixture,
) -> None:
    """WCS schedule refresh replaces in-memory events before pruning stale Redis entries."""
    sport = WCS(settings=settings.providers.sports)
    await sport.async_load_teams_from_source(wcs_teams_payload())
    stale_date = datetime(2026, 6, 15, 12, tzinfo=timezone.utc)
    stale_event = Event(
        sport="fifa",
        id=999,
        terms="stale",
        date=stale_date,
        original_date=stale_date.isoformat(),
        home_team={"key": "HOM", "id": 1, "name": "Home", "colors": []},
        away_team={"key": "AWY", "id": 2, "name": "Away", "colors": []},
        home_score=None,
        away_score=None,
        status=GameStatus.Scheduled,
        expiry=stale_date + timedelta(days=90),
        updated=stale_date,
    )
    sport.events = {stale_event.id: stale_event}
    # Preload rounds to avoid mocking external call
    sport.rounds = {1615: "Group Stage"}
    mock_cache = MagicMock(spec=RedisAdapter)
    mock_cache.zrange.return_value = [b"sport:wcs:v1:event:999"]
    sport.cache = mock_cache
    mocker.patch(
        "merino.providers.suggest.sports.backends.sportsdata.common.sports.get_data",
        new_callable=mocker.AsyncMock,
        return_value=wcs_schedule_payload(),
    )

    await sport.update_events(client=mock_client)

    assert set(sport.events) == {90011111, 90022222}
    mock_cache.delete.assert_called_once_with("sport:wcs:v1:event:999")
    mock_cache.zrem.assert_called_once_with("sport:wcs:v1:calendar", "sport:wcs:v1:event:999")


@freezegun.freeze_time("2026-06-10T00:00:00", tz_offset=0)
@pytest.mark.asyncio
async def test_wcs_update_events_empty_schedule_preserves_existing_cache(
    mock_client: AsyncClient,
    mocker: MockerFixture,
) -> None:
    """WCS schedule refresh skips cache writes when SportsData returns no schedule rows."""
    sport = WCS(settings=settings.providers.sports)
    stale_date = datetime(2026, 6, 15, 12, tzinfo=timezone.utc)
    stale_event = Event(
        sport="fifa",
        id=999,
        terms="stale",
        date=stale_date,
        original_date=stale_date.isoformat(),
        home_team={"key": "HOM", "id": 1, "name": "Home", "colors": []},
        away_team={"key": "AWY", "id": 2, "name": "Away", "colors": []},
        home_score=None,
        away_score=None,
        status=GameStatus.Scheduled,
        expiry=stale_date + timedelta(days=90),
        updated=stale_date,
    )
    sport.events = {stale_event.id: stale_event}
    # Preload rounds to avoid mocking external call
    sport.rounds = {1615: "Group Stage"}
    mock_cache = MagicMock(spec=RedisAdapter)
    sport.cache = mock_cache
    mocker.patch(
        "merino.providers.suggest.sports.backends.sportsdata.common.sports.get_data",
        new_callable=mocker.AsyncMock,
        return_value=[],
    )

    await sport.update_events(client=mock_client)

    assert sport.events == {stale_event.id: stale_event}
    mock_cache.set.assert_not_called()
    mock_cache.zadd.assert_not_called()
    mock_cache.delete.assert_not_called()
    mock_cache.zrem.assert_not_called()


@pytest.mark.asyncio
async def test_wcs_get_events_by_date_from_cache() -> None:
    """Test WCS event restoration from cached event keys."""
    sport = WCS(settings=settings.providers.sports)
    now = datetime(2026, 6, 15, 12, tzinfo=timezone.utc)
    event = Event(
        sport="fifa",
        id=123,
        terms="home away",
        date=now,
        original_date=now.isoformat(),
        home_team={"key": "HOM", "id": 1, "name": "Home", "colors": []},
        away_team={"key": "AWY", "id": 2, "name": "Away", "colors": []},
        home_score=2,
        away_score=1,
        status=GameStatus.Final,
        expiry=now + timedelta(days=90),
        updated=now,
        period="Regular",
        clock="90",
    )
    mock_cache = MagicMock(spec=RedisAdapter)
    mock_cache.zrange.return_value = [b"sport:wcs:v1:event:123"]
    mock_cache.mget.return_value = [sport.event_as_str(event).encode()]
    sport.cache = mock_cache

    start = now - timedelta(hours=1)
    end = now + timedelta(hours=1)
    result = await sport.get_events_by_date(start=start, end=end)

    assert len(result) == 1
    assert result[0].id == event.id
    assert result[0].period == "Regular"
    assert result[0].clock == "90"
    mock_cache.zrange.assert_called_once_with(
        "sport:wcs:v1:calendar",
        min=int(start.timestamp()),
        max=int(end.timestamp()),
    )
    mock_cache.mget.assert_called_once_with([b"sport:wcs:v1:event:123"])


@pytest.mark.asyncio
async def test_wcs_get_events_by_date_treats_naive_bounds_as_utc() -> None:
    """Naive datetime bounds are treated as UTC before querying the calendar."""
    sport = WCS(settings=settings.providers.sports)
    mock_cache = MagicMock(spec=RedisAdapter)
    mock_cache.zrange.return_value = []
    sport.cache = mock_cache

    start = datetime(2026, 6, 15, 11)
    end = datetime(2026, 6, 15, 13)
    result = await sport.get_events_by_date(start=start, end=end)

    assert result == []
    mock_cache.zrange.assert_called_once_with(
        "sport:wcs:v1:calendar",
        min=int(start.replace(tzinfo=timezone.utc).timestamp()),
        max=int(end.replace(tzinfo=timezone.utc).timestamp()),
    )


@pytest.mark.asyncio
async def test_wcs_fix_country_codes() -> None:
    """Test that we return corrected country codes"""
    sport = WCS(settings=settings.providers.sports)
    mock_cache = MagicMock(spec=RedisAdapter)
    mock_cache.hgetall.side_effect = [
        {b"name": "Cabo Verde".encode(), b"code": b"CVI"},
        {b"name": "DR Congo".encode(), b"code": b"CDR"},
    ]
    sport.cache = mock_cache

    # code doesn't really matter, but let's be consistent and pretend it does.
    result = await sport.get_country(44)
    assert cast(dict, result)[b"code"] == b"CPV"
    result = await sport.get_country(53)
    assert cast(dict, result)[b"code"] == b"COD"


@freezegun.freeze_time("2025-09-22T00:00:00", tz_offset=0)
@pytest.mark.asyncio
async def test_weird_afc_update_events(
    weird_schedules_payload: list[dict],
    mock_client: AsyncClient,
    mocker: MockerFixture,
) -> None:
    """Test UCL event updates."""
    sport = NFL(settings=settings.providers.sports)
    sport.load_teams_from_source(nfl_teams_payload())
    sport.season = "2025"  # set by update_teams normally
    sport.event_ttl = timedelta(weeks=2)

    mocker.patch(
        "merino.providers.suggest.sports.backends.sportsdata.common.sports.get_data",
        side_effect=[weird_schedules_payload, nfl_scores_payload()],
    )
    await sport.update_events(client=mock_client)
    assert not sport.events


@pytest.mark.asyncio
async def test_sport_no_season(mock_client: AsyncClient, mocker: MockerFixture):
    """Test sport events with no season"""
    sport = NFL(settings=settings.providers.sports)
    timeframe = [
        {
            "SeasonType": 4,
            "Season": 2025,
            "Week": None,
            "Name": "Draft",
            "ApiSeason": "2025REG",
            "ApiWeek": None,
            "StartDate": "2025-09-17T00:00:00",
            "EndDate": "2025-09-23T23:59:59",
        }
    ]
    _get_data = mocker.patch(
        "merino.providers.suggest.sports.backends.sportsdata.common.sports.get_data",
        side_effect=[timeframe],
    )

    await sport.get_season(client=mock_client)

    assert sport.week is None


def test_sport_subclasses_have_category_mapping() -> None:
    """Assert every Sport subclass in sports.py has an entry in SPORT_CATEGORY_MAP.

    Catches the case where a new Sport class is added but the static map is not updated.
    """
    missing = [
        cls.__name__
        for cls in Sport.__subclasses__()
        if cls.__module__ == sports_module.__name__ and cls.__name__ not in SPORT_CATEGORY_MAP
    ]
    assert missing == [], f"Sport subclasses missing from SPORT_CATEGORY_MAP: {missing}"


@pytest.mark.asyncio
async def test_sportsdata_errors() -> None:
    """Test that the warning and error wrappers work."""
    warning = SportsDataWarning("Foo")
    assert isinstance(warning, Exception)
    assert str(warning) == "SportsDataWarning: Foo"

    error = SportsDataError("Foo")
    assert isinstance(error, Exception)
    assert str(error) == "SportsDataError: Foo"


def test_sport_term_pollution() -> None:
    """Test that the translate terms don't cross pollute"""
    sport = NFL(settings=settings.providers.sports)
    terms = sport.normalized_terms.copy()
    sport2 = MLB(settings=settings.providers.sports)
    assert sport.normalized_terms != sport2.normalized_terms
    assert sport.normalized_terms == terms
