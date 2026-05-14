"""Unit Test for Sports Data models."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import freezegun
import pytest

from merino.configs import settings
from merino.providers.suggest.sports.backends.sportsdata.common import GameStatus
from merino.providers.suggest.sports.backends.sportsdata.common.data import (
    Team,
    Sport,
    SportNormalizedTerms,
    SportsDataEventRow,
    SPORTSDATA_US_EASTERN,
    sportsdata_day_slug,
)
from merino.providers.suggest.sports.backends.sportsdata.common.sports import (
    NFL,
    NHL,
    NBA,
    MLB,
    UCL,
)


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
    # NOTE: Since this data is testing the general function, we are feeding it artificial constructs
    # with all variations populated.
    # Please refer to `test_sports` for more accurate data returns from the provider.

    return [
        {
            "GameID": 11111,
            "Season": 2026,
            "SeasonType": 2,
            "Status": "Final",
            "Day": "2025-09-21T00:00:00",
            "DateTime": "2025-09-21T21:30:00",
            "Updated": "2025-09-29T04:10:57",
            "IsClosed": True,
            "AwayTeam": "AWA",
            "AwayTeamId": 456,
            "AwayTeamID": 456,
            "HomeTeam": "HOM",
            "HomeTeamId": 123,
            "HomeTeamID": 123,
            "StadiumID": 9,
            "AwayScore": 2,
            "HomeScore": 3,
            "AwayTeamScore": 2,
            "HomeTeamScore": 3,
            "AwayTeamRuns": 2,
            "HomeTeamRuns": 3,
            "GlobalGameID": 11111,
            "GlobalGameId": 11111,
            "GlobalAwayTeamID": 456,
            "GlobalHomeTeamID": 123,
            "GlobalAwayTeamId": 456,
            "GlobalHomeTeamId": 123,
            "GameEndDateTime": "2025-09-22T00:10:17",
            "NeutralVenue": False,
            # "DateTimeUTC": "2025-09-22T01:30:00", # Exercise the `DateTime` recovery statement
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
            "AwayTeamId": 456,
            "AwayTeamID": 456,
            "HomeTeam": "HOM",
            "HomeTeamId": 123,
            "HomeTeamID": 123,
            "StadiumID": 9,
            "AwayScore": 0,
            "HomeScore": 0,
            "AwayTeamScore": 0,
            "HomeTeamScore": 0,
            "AwayTeamRuns": 0,
            "HomeTeamRuns": 0,
            "GlobalGameID": 22222,
            "GlobalGameId": 22222,
            "GlobalAwayTeamID": 456,
            "GlobalHomeTeamID": 123,
            "GlobalAwayTeamId": 456,
            "GlobalHomeTeamId": 123,
            "GameEndDateTime": "2000-09-22T00:10:17",
            "NeutralVenue": False,
            "DateTimeUTC": "2000-09-22T01:30:00",
            "SeriesInfo": None,
        },
        {
            "GameID": 33333,
            "Season": 2000,
            "SeasonType": 2,
            "Status": "Canceled",
            "Day": None,
            "DateTime": None,
            "Updated": "2025-01-02T04:10:57",
            "IsClosed": True,
            "AwayTeam": "AWA",
            "AwayTeamId": 456,
            "AwayTeamID": 456,
            "HomeTeam": "HOM",
            "HomeTeamId": 123,
            "HomeTeamID": 123,
            "StadiumID": 9,
            "AwayScore": 0,
            "HomeScore": 0,
            "AwayTeamScore": 0,
            "HomeTeamScore": 0,
            "AwayTeamRuns": 0,
            "HomeTeamRuns": 0,
            "GlobalGameID": 33333,
            "GlobalGameId": 33333,
            "GlobalAwayTeamID": 456,
            "GlobalHomeTeamID": 123,
            "GlobalAwayTeamId": 456,
            "GlobalHomeTeamId": 123,
            "GameEndDateTime": None,
            "NeutralVenue": False,
            "DateTimeUTC": None,
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
        id=123,
        key="HOM",
        locale="AA",
        aliases=["Home Team", "Home", "AA Home Team"],
        colors=[],
        updated=datetime(2025, 9, 21, 10, 30, 00),
        expiry=1760502209,
        country=None,
    )


@pytest.fixture(name="away_team")
def away_team_fixture():
    """Away team fixture."""
    return Team(
        fullname="The Away Team",
        terms="Away Team",
        name="Away Team",
        id=456,
        key="AWA",
        locale="BB",
        aliases=["Away Team", "Away Team", "BB Away Team"],
        colors=[],
        updated=datetime(2025, 9, 22, 10, 30, 00),
        expiry=1760502209,
        country=None,
    )


@pytest.fixture(name="teams")
def teams_fixture():
    """Teams fixture."""
    return [
        {
            "Key": "HOM",
            "Name": "Home",
            "City": "Toronto",
            "TeamID": 123,
            "GlobalTeamID": 123,
            "GlobalTeamId": 123,
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
            "TeamID": 456,
            "GlobalTeamID": 456,
            "GlobalTeamId": 456,
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
    sport = sport_cls(settings=settings.providers.sports, name="", base_url="")
    sport.teams = {
        123: home_team,
        456: away_team,
    }

    sport.events = {}
    events = sport.load_schedules_from_source(events_response)

    assert 11111 in events
    assert 22222 not in events
    assert 33333 not in events

    sport.events = {}
    score_events = sport.load_scores_from_source(events_response)
    assert 11111 in score_events
    assert 22222 not in score_events
    assert 33333 not in score_events

    ev = events[11111]

    assert ev.status == GameStatus.Final
    assert ev.home_team["key"] == "HOM"
    assert ev.away_team["key"] == "AWA"
    assert ev.home_score == 3
    assert ev.away_score == 2

    sport.events = {}
    mod_event = events_response[0]

    mod_event["DateTimeUTC"] = None
    mod_event["DateTime"] = None
    sport.events = {}
    # Ensure that events without valid timestamps are not loaded.
    mod_events = sport.load_schedules_from_source(
        [mod_event], event_timezone=ZoneInfo("America/New_York")
    )
    assert len(mod_events) == 0


def test_sportsdata_event_rows_keep_mlb_kickoff_and_freshness_separate() -> None:
    """Late ET MLB games keep UTC kickoffs and independent source freshness."""
    sport = MLB(settings=settings.providers.sports, name="", base_url="")
    may_11_row = SportsDataEventRow.from_event_description(
        {
            "AwayTeamRuns": 9,
            "HomeTeamRuns": 3,
            "GameID": 77896,
            "Status": "Final",
            "Day": "2026-05-11T00:00:00",
            "DateTime": "2026-05-11T22:10:00",
            "DateTimeUTC": "2026-05-12T02:10:00",
            "AwayTeam": "SF",
            "HomeTeam": "LAD",
            "AwayTeamID": 15,
            "HomeTeamID": 1,
            "Updated": "2026-05-13T07:58:54",
        },
        normalized_terms=sport.normalized_terms,
        event_timezone=SPORTSDATA_US_EASTERN,
    )
    may_12_row = SportsDataEventRow.from_event_description(
        {
            "AwayTeamRuns": 6,
            "HomeTeamRuns": 2,
            "GameID": 77908,
            "Status": "Final",
            "Day": "2026-05-12T00:00:00",
            "DateTime": "2026-05-12T22:10:00",
            "DateTimeUTC": "2026-05-13T02:10:00",
            "AwayTeam": "SF",
            "HomeTeam": "LAD",
            "AwayTeamID": 15,
            "HomeTeamID": 1,
            "Updated": "2026-05-13T07:31:32",
        },
        normalized_terms=sport.normalized_terms,
        event_timezone=SPORTSDATA_US_EASTERN,
    )

    assert may_11_row.kickoff == datetime(2026, 5, 12, 2, 10, tzinfo=timezone.utc)
    assert sportsdata_day_slug(may_11_row.kickoff, SPORTSDATA_US_EASTERN) == "2026-MAY-11"
    assert may_11_row.original_date == "2026-05-11T00:00:00"
    assert may_11_row.away_score == 9
    assert may_11_row.home_score == 3
    assert may_11_row.updated == datetime(2026, 5, 13, 11, 58, 54, tzinfo=timezone.utc)

    assert may_12_row.kickoff == datetime(2026, 5, 13, 2, 10, tzinfo=timezone.utc)
    assert sportsdata_day_slug(may_12_row.kickoff, SPORTSDATA_US_EASTERN) == "2026-MAY-12"
    assert may_12_row.original_date == "2026-05-12T00:00:00"
    assert may_12_row.away_score == 6
    assert may_12_row.home_score == 2
    assert may_12_row.updated == datetime(2026, 5, 13, 11, 31, 32, tzinfo=timezone.utc)

    assert may_11_row.updated > may_12_row.updated
    assert may_11_row.kickoff < may_12_row.kickoff


def test_sportsdata_event_row_allows_missing_updated_time() -> None:
    """SportsData rows may omit source freshness timestamps."""
    sport = MLB(settings=settings.providers.sports, name="", base_url="")
    row = SportsDataEventRow.from_event_description(
        {
            "AwayTeamRuns": 6,
            "HomeTeamRuns": 2,
            "GameID": 77908,
            "Status": "Final",
            "DateTime": "2026-05-12T22:10:00",
            "DateTimeUTC": "2026-05-13T02:10:00",
            "AwayTeam": "SF",
            "HomeTeam": "LAD",
            "AwayTeamID": 15,
            "HomeTeamID": 1,
        },
        normalized_terms=sport.normalized_terms,
        event_timezone=SPORTSDATA_US_EASTERN,
    )

    assert row.updated is None


def test_event_row_from_source_logs_invalid_event_for_missing_game_id(caplog) -> None:
    """Rows without SportsData game IDs are invalid events, not date failures."""
    caplog.set_level("INFO")
    sport = MLB(settings=settings.providers.sports, name="", base_url="")

    row = sport.event_row_from_source(
        {
            "Status": "Final",
            "DateTimeUTC": "2026-05-13T02:10:00",
            "AwayTeam": "SF",
            "HomeTeam": "LAD",
            "AwayTeamID": 15,
            "HomeTeamID": 1,
        },
        event_timezone=SPORTSDATA_US_EASTERN,
    )

    assert row is None
    assert "sports.error.invalid_event" in caplog.text
    assert "sports.error.no_date" not in caplog.text


def test_event_row_from_source_logs_no_date_for_missing_kickoff(caplog) -> None:
    """Rows without a usable kickoff timestamp remain date failures."""
    caplog.set_level("INFO")
    sport = MLB(settings=settings.providers.sports, name="", base_url="")

    row = sport.event_row_from_source(
        {
            "GameID": 77908,
            "Status": "Final",
            "AwayTeam": "SF",
            "HomeTeam": "LAD",
            "AwayTeamID": 15,
            "HomeTeamID": 1,
        },
        event_timezone=SPORTSDATA_US_EASTERN,
    )

    assert row is None
    assert "sports.error.no_date" in caplog.text
    assert "sports.error.invalid_event" not in caplog.text


@freezegun.freeze_time("2025-09-22T00:00:00", tz_offset=0)
@pytest.mark.parametrize(
    "sport_cls", [NFL, NHL, NBA, MLB, UCL], ids=["NFL", "NHL", "NBA", "MLB", "UCL"]
)
def test_load_incomplete_schedules_from_source(
    sport_cls: type[Sport],
    events_response: list[dict],
    home_team: Team,
    away_team: Team,
):
    """Ensure we drop events with incorrect team IDs"""
    sport = sport_cls(settings=settings.providers.sports, name="", base_url="")
    sport.teams = {
        000: home_team,
        456: away_team,
    }
    sport.events = {}
    events = sport.load_schedules_from_source(events_response)
    assert not events

    sport.events = {}
    events = sport.load_scores_from_source(events_response)
    assert not events

    sport.teams = {
        123: home_team,
        456: away_team,
    }

    # Remove all traces of the "away" team from the test data, because there can be a lot.
    away_keys = list(filter(lambda x: "awayteam" in x.lower(), events_response[0].keys()))
    for key in away_keys:
        del events_response[0][key]
    sport.events = {}
    events = sport.load_scores_from_source(events_response)
    assert not events

    sport.events = {}
    events = sport.load_schedules_from_source(events_response)
    assert not events


@freezegun.freeze_time("2025-09-22T00:00:00", tz_offset=0)
@pytest.mark.parametrize(
    "sport_cls", [NFL, NHL, NBA, MLB, UCL], ids=["NFL", "NHL", "NBA", "MLB", "UCL"]
)
def test_load_teams_from_source(
    sport_cls: type[Sport],
    teams: list[dict],
):
    """Ensure teams are loaded correctly."""
    sport = sport_cls(settings=settings.providers.sports, name="", base_url="")
    teams_data = sport.load_teams_from_source(teams)

    assert set(teams_data.keys()) == {456, 123}


@freezegun.freeze_time("2025-09-22T00:00:00", tz_offset=0)
@pytest.mark.parametrize("sport_cls", [NFL, NHL, NBA], ids=["NFL", "NHL", "NBA"])
def test_load_bad_teams_from_source(
    sport_cls: type[Sport],
    events_response: list[dict],
    teams: list[dict],
    home_team: Team,
    away_team: Team,
):
    """Ensure bad teams are not loaded."""
    sport = sport_cls(settings=settings.providers.sports, name="", base_url="")
    keys = list(filter(lambda x: "teamid" in x.lower(), teams[0].keys()))
    for key in keys:
        del teams[0][key]
    teams_data = sport.load_teams_from_source(teams)

    assert set(teams_data.keys()) == {456}


@pytest.mark.parametrize(
    "name,expected_key",
    [
        ("Korea Republic", "KOR"),
        ("Curaçao", "CUW"),
    ],
    ids=["korea-keeps-kor", "curacao-remapped-to-cuw"],
)
def test_from_data_disambiguates_kor_collision(name: str, expected_key: str) -> None:
    """Verify Curaçao is remapped to CUW while Korea keeps KOR.

    sportsdata's international-soccer feed returns Key=KOR for both Korea
    Republic and Curaçao, so Team.from_data must disambiguate by Name to keep
    the two teams distinct downstream.
    """
    team = Team.from_data(
        {
            "Key": "KOR",
            "Name": name,
            "AreaName": name,
            "TeamID": 12345,
        },
        term_filter=[],
        team_ttl=timedelta(weeks=1),
        normalized_terms=SportNormalizedTerms,
    )
    assert team.key == expected_key
