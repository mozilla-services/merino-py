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
import merino.providers.suggest.sports.backends.sportsdata.common.sports as sports_module
from merino.providers.suggest.sports.backends.sportsdata.common.sports import (
    NFL,
    NHL,
    NBA,
    UCL,
    MLB,
    FIFA,
    SPORT_CATEGORY_MAP,
)


@pytest.fixture
def mock_client(mocker: MockerFixture) -> AsyncClient:
    """Mock Async Client."""
    return cast(AsyncClient, mocker.Mock(spec=AsyncClient))


@pytest.fixture
def generic_teams_payload() -> list[dict]:
    """Provide Generic team payload (for US based sports)."""
    return [
        {
            "Key": "HOM",
            "Name": "Homebodies",
            "City": "Springfield",
            "AreaName": "US",
            "FullName": "Springfield Homebodies",
            "Nickname1": "Homers",
            "GlobalTeamId": 98,
            "PrimaryColor": "000000",
            "SecondaryColor": "FFFFFF",
        },
        {
            "Key": "AWY",
            "Name": "Visitors",
            "City": "Elsewhere",
            "AreaName": "OS",
            "GlobalTeamId": 99,
            "FullName": "Visitors from Elsewhere",
            "PrimaryColor": "FFFFFF",
            "SecondaryColor": "000000",
        },
    ]


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


def fifa_teams_payload() -> list[dict]:
    """Return FIFA/WC sample team data"""
    # https://api.sportsdata.io/v4/soccer/scores/json/Teams/FIFA?key=
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


def fifa_schedule_payload() -> list[dict]:
    """Return FIFA/WC sample schedule data"""
    # https://api.sportsdata.io/v4/soccer/scores/json/SchedulesBasic/FIFA/2026?key=...
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


def fifa_score_payload() -> list[dict]:
    """Return FIFA/WC sample score data"""
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
    assert set(nfl.teams.keys()) == {1, 2}
    t1 = nfl.teams[1]
    assert t1.name == "Cardinals"
    assert get_data.call_count == 2
    assert "/Timeframes/current" in get_data.call_args_list[0].kwargs["url"]
    assert "/Teams?key=" in get_data.call_args_list[1].kwargs["url"]


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
    out = await nhl.update_teams(client=mock_client)
    assert out is nhl
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
        side_effect=[teams_payload],  # called twice per code
    )
    await ucl.update_teams(client=mock_client)
    assert ucl.season == "2025"
    assert set(ucl.teams.keys()) == {90000001, 90000002}
    assert get_data.call_count == 1

    assert "/Teams/ucl?key=" in get_data.call_args_list[0].kwargs["url"]


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

    nhl = NHL(settings=settings.providers.sports)
    nhl.load_teams_from_source(teams_payload)
    nhl.season = "2026PRE"
    nhl.event_ttl = timedelta(weeks=2)

    get_data = mocker.patch(
        "merino.providers.suggest.sports.backends.sportsdata.common.sports.get_data",
        side_effect=[schedules_payload, scores_payload],
    )

    await nhl.update_events(client=mock_client)
    assert 11111 in nhl.events and 0 not in nhl.events
    ev = nhl.events[11111]
    assert ev.status == GameStatus.Final
    assert ev.home_team["key"] == "BUF"
    assert ev.away_team["key"] == "BOS"
    assert 2 == get_data.call_count
    for call in get_data.call_args_list:
        assert call.kwargs["url"] in [
            "https://api.sportsdata.io/v3/nhl/scores/json/SchedulesBasic/2026PRE?key=",
            "https://api.sportsdata.io/v3/nhl/scores/json/GamesByDate/2025-SEP-22?key=",
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
    for call in get_data.call_args_list:
        assert call.kwargs["url"] in [
            "https://api.sportsdata.io/v3/nba/scores/json/SchedulesBasic/2026PRE?key=",
            "https://api.sportsdata.io/v3/nba/scores/json/ScoresBasic/2025-SEP-22?key=",
        ]


@freezegun.freeze_time("2025-09-22T00:00:00", tz_offset=0)
@pytest.mark.asyncio
async def test_mlb_update_events(
    mock_client: AsyncClient,
    mocker: MockerFixture,
) -> None:
    """Test MLB event updates."""
    sport = MLB(settings=settings.providers.sports)
    sport.load_teams_from_source(mlb_teams_payload())
    sport.season = "2026PRE"
    sport.event_ttl = timedelta(weeks=2)

    # schedules_payload = mlb_schedule_payload()
    scores_payload = mlb_score_payload()
    within = "2025-09-22T13:30:00"  # UTC
    outside = "2026-01-22T13:30:00"
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
        side_effect=[scores_payload],
    )

    await sport.update_events(client=mock_client)
    assert 11111 in sport.events and 22222 not in sport.events
    assert sport.events[11111].status == GameStatus.Final
    get_data.assert_called_once()


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
    assert "/SchedulesBasic/UCL/2025?key=" in get_data.call_args_list[0].kwargs["url"]


@freezegun.freeze_time("2025-09-22T00:00:00", tz_offset=0)
@pytest.mark.asyncio
async def test_fifa_update_events(
    mock_client: AsyncClient,
    mocker: MockerFixture,
) -> None:
    """Test FIFA event updates."""
    ucl = FIFA(settings=settings.providers.sports)
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
    assert str(warning) == "SportsDataWarning: Foo"

    error = SportsDataError("Foo")
    assert str(error) == "SportsDataError: Foo"


def test_sport_term_pollution() -> None:
    """Test that the translate terms don't cross pollute"""
    sport = NFL(settings=settings.providers.sports)
    terms = sport.translate_terms.copy()
    sport2 = MLB(settings=settings.providers.sports)
    assert sport.translate_terms != sport2.translate_terms
    assert sport.translate_terms == terms
