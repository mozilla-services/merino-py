"""Test Gauntlet for SportsData.io"""

import os

import freezegun
import pytest
import json
from datetime import datetime, timedelta, timezone

from unittest.mock import patch, AsyncMock

import httpx

from unittest.mock import MagicMock
from pytest_mock import MockerFixture
from typing import cast

from merino.configs import settings
from merino.providers.suggest.sports.backends import get_data
from merino.providers.suggest.sports.backends.sportsdata.backend import (
    SportsDataBackend,
)
from merino.providers.suggest.sports.backends.sportsdata.common import GameStatus
from merino.providers.suggest.sports.backends.sportsdata.common.data import Team
from merino.providers.suggest.sports.backends.sportsdata.common.elastic import (
    SportsDataStore,
)


VALID_TEST_RESPONSE: dict = {}


@pytest.mark.asyncio
async def test_get_data():
    """Simple test for the `get_data` caching fetcher."""
    ttl = timedelta(seconds=5)
    with patch.object(
        httpx.AsyncClient,
        "get",
        return_value=httpx.Response(status_code=200, json=dict(foo="bar")),
    ) as mock_client:
        mock_res = {"foo": "bar"}
        with patch.object(json, "dump") as mock_json:
            await get_data(
                client=mock_client,
                url="http://example.org",
                ttl=ttl,
                cache_dir="/tmp",  # nosec
            )
            # was the URL called?
            mock_client.get.assert_called_with("http://example.org")
            # see if it tried to write the file to the cache dir...
            assert (
                mock_json.call_args_list[0].args[1].buffer.name
                == "/tmp/ff7c1f10ab54968058fdcfaadf1b2457cd5d1a3f.json"  # nosec
            )
            with patch.object(json, "load") as mock_load:
                mock_load.return_value = mock_res
                ttl = timedelta(days=5)
                res = await get_data(
                    client=mock_client,
                    url="http://example.org",
                    ttl=ttl,
                    cache_dir="/tmp",  # nosec
                )
                assert mock_load.call_count == 1
                assert res == mock_res


@pytest.mark.asyncio
async def test_get_data_with_no_cache_dir():
    """Test for `get_data` with no cache dir."""
    ttl = timedelta(seconds=5)
    with patch.object(
        httpx.AsyncClient,
        "get",
        return_value=httpx.Response(status_code=200, json=dict(foo="bar")),
    ) as mock_client:
        with patch.object(json, "dump") as mock_json:
            await get_data(
                client=mock_client,
                url="http://example.org",
                ttl=ttl,
            )
            mock_client.get.assert_called_with("http://example.org")
            mock_json.assert_not_called()


@pytest.mark.asyncio
async def test_get_data_handles_permission_error():
    """Test for `get_data` handles permission error."""
    ttl = timedelta(seconds=5)
    with patch.object(
        httpx.AsyncClient,
        "get",
        return_value=httpx.Response(status_code=200, json=dict(foo="bar")),
    ) as mock_client:
        with (
            patch.object(os.path, "exists", return_value=True),
            patch.object(os.path, "getctime", side_effect=PermissionError),
            patch.object(json, "dump"),
        ):
            await get_data(
                client=mock_client,
                url="http://example.org",
                ttl=ttl,
                cache_dir="/tmp",  # nosec
            )
            # Permission Error file not read, request need to be made
            mock_client.get.assert_called_with("http://example.org")


@pytest.mark.asyncio
@freezegun.freeze_time("2025-09-22T00:00:00", tz_offset=0)
async def test_get_data_cache_file_exists():
    """Test for `get_data` handles cache file exists."""
    ttl = timedelta(days=1)
    with patch.object(
        httpx.AsyncClient,
        "get",
        return_value=httpx.Response(status_code=200, json=dict(foo="bar")),
    ) as mock_client:
        with (
            patch.object(os.path, "exists", return_value=True),
            patch.object(os.path, "getctime", return_value=datetime.now().timestamp()),
            patch.object(json, "load", return_value={"bar": "foo"}),
        ):
            data = await get_data(
                client=mock_client,
                url="http://example.org",
                ttl=ttl,
                cache_dir="/tmp",  # nosec
            )
            mock_client.get.assert_not_called()
            assert data == {"bar": "foo"}


# sports/backends/sportsdata/common:
@pytest.mark.asyncio
async def test_gamestatus():
    """Test the GameStatus enum"""
    assert GameStatus.parse("final") == GameStatus.Final
    assert GameStatus.parse("in progress") == GameStatus.InProgress
    assert GameStatus.parse("final - over time") == GameStatus.F_OT
    assert GameStatus.parse("final - shoot out") == GameStatus.F_SO
    assert GameStatus.parse("not necessary") == GameStatus.NotNecessary
    assert GameStatus.parse("Banana") == GameStatus.Unknown

    assert GameStatus.Final.is_final()
    assert GameStatus.parse("scheduled").is_scheduled()
    assert GameStatus.parse("suspended").is_in_progress()
    assert GameStatus.parse("In Progress").status_type() == GameStatus.InProgress
    assert GameStatus.NotNecessary.as_str() == "Not Necessary"
    assert GameStatus.Final.status_type() == GameStatus.Final
    assert GameStatus.F_OT.status_type() == GameStatus.Final
    assert GameStatus.Scheduled.status_type() == GameStatus.Scheduled

    assert GameStatus.Final.as_ui_status() == "past"
    assert GameStatus.InProgress.as_ui_status() == "live"
    assert GameStatus.Scheduled.as_ui_status() == "scheduled"
    assert GameStatus.Unknown.as_ui_status() == "unknown"

    assert GameStatus.InProgress.as_str() == "In Progress"
    assert GameStatus.F_OT.as_str() == "Final - Over Time"
    assert GameStatus.F_SO.as_str() == "Final - Shoot Out"
    assert GameStatus.NotNecessary.as_str() == "Not Necessary"
    assert GameStatus.Unknown.as_str() == ""
    assert GameStatus.Canceled.as_str() == "Canceled"


@pytest.mark.asyncio
async def test_team():
    """Test the team parser"""
    team_data = {
        "TeamId": 694,
        "AreaId": 203,
        "VenueId": 437,
        "Key": "CHI",
        "Name": "Chicago Fire FC",
        "FullName": "Chicago Fire Football Club",
        "Active": True,
        "AreaName": "United States",
        "VenueName": "Soldier Field",
        "Gender": "Male",
        "Type": "Club",
        "Address": None,
        "City": "Chicago",
        "Zip": None,
        "Phone": None,
        "Fax": None,
        "Website": "http://www.chicago-fire.com",
        "Email": None,
        "Founded": 1997,
        "ClubColor1": "FF0000",
        "ClubColor2": "FFFFFF",
        "ClubColor3": None,
        "Nickname1": "The Fire",
        "Nickname2": "La Máquina Roja",
        "Nickname3": "Men in Red",
        "WikipediaLogoUrl": "https://upload.wikimedia.org/wikipedia/commons/0/03/Chicago_Fire_logo%2C_2021.svg",
        "WikipediaWordMarkUrl": None,
        "GlobalTeamId": 90000694,
    }
    ttl = timedelta(seconds=300)
    team = Team.from_data(team_data=team_data, term_filter=["La", "The", "fc"], team_ttl=ttl)
    assert team.key == "CHI"
    assert team.locale == "Chicago United States"
    assert team.colors == ["FF0000", "FFFFFF"]
    assert "fire" in team.terms
    assert "chicago" in team.terms
    assert team.minimal() == {
        "key": "CHI",
        "name": "Chicago Fire Football Club",
        "colors": ["FF0000", "FFFFFF"],
    }


@pytest.fixture(name="es_client")
def fixture_es_client(mocker: MockerFixture) -> MagicMock:
    """Test ElasticSearch client instance."""
    client = mocker.MagicMock()
    client.close = mocker.AsyncMock()

    indices = mocker.MagicMock()
    indices.create = mocker.AsyncMock()
    indices.delete = mocker.AsyncMock()
    indices.refresh = mocker.AsyncMock()
    client.indices = indices

    client.delete_by_query = mocker.AsyncMock()
    client.search = mocker.AsyncMock()
    return cast(MagicMock, client)


@pytest.fixture(name="sport_data_store")
def fixture_sport_data_store(es_client: MagicMock) -> SportsDataStore:
    """Test Sport Data Store instance"""
    s = SportsDataStore(
        dsn="http://es.test:9200",
        api_key="test-key",
        languages=["en"],
        platform="test",
        index_map={"event": "sports-en-events-test"},
    )
    s.client = es_client
    return s


@pytest.mark.asyncio
async def test_sportsdata_backend(sport_data_store: SportsDataStore, mocker: MockerFixture):
    """Test the backend"""
    sport_data_store.search_events = AsyncMock(  # type: ignore
        side_effect=[
            {
                "all": {
                    "previous": {
                        "sport": "NHL",
                        "id": 30024036,
                        "date": 1760655600,
                        "home_team": {
                            "key": "PHI",
                            "name": "Philadelphia Flyers",
                            "colors": ["D24303", "000000", "FFFFFF"],
                        },
                        "away_team": {
                            "key": "WPG",
                            "name": "Winnipeg Jets",
                            "colors": ["041E42", "004A98", "A2AAAD", "A6192E"],
                        },
                        "home_score": 2,
                        "away_score": 5,
                        "status": "Final",
                        "expiry": 1760921459,
                        "es_score": 3.3510802,
                        "event_status": GameStatus.Final,
                    },
                    "next": {
                        "sport": "NFL",
                        "id": 19175,
                        "date": 1761498000,
                        "home_team": {
                            "key": "CIN",
                            "name": "Cincinnati Bengals",
                            "colors": ["000000", "FB4F14", "FFFFFF"],
                        },
                        "away_team": {
                            "key": "NYJ",
                            "name": "New York Jets",
                            "colors": ["115740", "FFFFFF", "000000"],
                        },
                        "home_score": None,
                        "away_score": None,
                        "status": "Scheduled",
                        "expiry": 1761958258,
                        "es_score": 3.0596066,
                        "event_status": GameStatus.Scheduled,
                    },
                }
            }
        ]
    )

    backend = SportsDataBackend(settings=settings.providers.sports, store=sport_data_store)
    res = await backend.query(
        query_string="Some Search String",
    )
    assert len(res) == 1
    summary = res[0]
    assert summary.sport == "all"
    assert len(summary.values) == 2


@freezegun.freeze_time("2025-09-22T00:00:00", tz_offset=0)
@pytest.mark.asyncio
async def test_sports_backend_startup(sport_data_store: SportsDataStore, mocker: MockerFixture):
    """Test the sports backend startup process with mocked sports classes."""
    # Patch the sport classes
    # mock_nba_class = mocker.patch(
    #    "merino.providers.suggest.sports.backends.sportsdata.backend.NBA"
    # )
    # mock_nfl_class = mocker.patch(
    #   "merino.providers.suggest.sports.backends.sportsdata.backend.NFL"
    # )
    mock_nhl_class = mocker.patch(
        "merino.providers.suggest.sports.backends.sportsdata.backend.NHL"
    )
    # mock_nba_instance = AsyncMock()
    # mock_nfl_instance = AsyncMock()
    mock_nhl_instance = AsyncMock()

    # Set the name attribute for each mock instance
    # mock_nba_instance.name = "NBA"
    # mock_nfl_instance.name = "NFL"
    mock_nhl_instance.name = "NHL"

    # Configure the class constructors to return the mock instances
    # mock_nba_class.return_value = mock_nba_instance
    # mock_nfl_class.return_value = mock_nfl_instance
    mock_nhl_class.return_value = mock_nhl_instance

    # Setup async methods on the instances
    # mock_nba_instance.update_teams = AsyncMock()
    # mock_nfl_instance.update_teams = AsyncMock()
    mock_nhl_instance.update_teams = AsyncMock()
    # mock_nba_instance.update_events = AsyncMock()
    # mock_nfl_instance.update_events = AsyncMock()
    mock_nhl_instance.update_events = AsyncMock()

    # Mock the HTTP client
    mock_client = AsyncMock()
    mocker.patch(
        "merino.providers.suggest.sports.backends.sportsdata.backend.create_http_client",
        return_value=mock_client,
    )

    # Configure the SportsDataStore fixture
    timestamp = (datetime.now(tz=timezone.utc) + timedelta(minutes=5)).timestamp()
    mock_startup = AsyncMock(return_value=True)
    mock_query_meta = AsyncMock(side_effect=[None, timestamp, timestamp])
    mock_store_meta = AsyncMock()
    mock_store_events = AsyncMock()

    mocker.patch.object(sport_data_store, "startup", new=mock_startup)
    mocker.patch.object(sport_data_store, "query_meta", new=mock_query_meta)
    mocker.patch.object(sport_data_store, "store_meta", new=mock_store_meta)
    mocker.patch.object(sport_data_store, "store_events", new=mock_store_events)

    # Create and test the backend
    backend = SportsDataBackend(settings=settings.providers.sports, store=sport_data_store)
    await backend.startup()

    # Verify the mocked classes were instantiated
    # mock_nba_class.assert_called_once_with(settings=settings.providers.sports)
    # mock_nfl_class.assert_called_once_with(settings=settings.providers.sports)
    mock_nhl_class.assert_called_once_with(settings=settings.providers.sports)

    # Verify async methods were called on each sport instance
    # mock_nba_instance.update_teams.assert_called_once_with(client=mock_client)
    # mock_nfl_instance.update_teams.assert_called_once_with(client=mock_client)
    mock_nhl_instance.update_teams.assert_called_once_with(client=mock_client)
    # mock_nba_instance.update_events.assert_called_once_with(client=mock_client)
    # mock_nfl_instance.update_events.assert_called_once_with(client=mock_client)
    mock_nhl_instance.update_events.assert_called_once_with(client=mock_client)

    # Verify store_events was called for each sport
    # assert mock_store_events.call_count == 3
    assert mock_store_events.call_count == 1
    # mock_store_events.assert_any_call(mock_nba_instance, language_code="en")
    # mock_store_events.assert_any_call(mock_nfl_instance, language_code="en")
    mock_store_events.assert_any_call(mock_nhl_instance, language_code="en")
