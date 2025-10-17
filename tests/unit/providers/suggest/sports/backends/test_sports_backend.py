"""Test Gauntlet for SportsData.io"""

import pytest
import json
from datetime import datetime, timedelta, timezone


from unittest.mock import patch
import httpx

# from merino.configs import settings
from merino.providers.suggest.sports.backends import get_data
from merino.providers.suggest.sports.backends.sportsdata.common import GameStatus
from merino.providers.suggest.sports.backends.sportsdata.common.data import (
    SportDate,
    Team,
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
            # TODO: check for TTL.


@pytest.mark.asyncio
async def test_build_suggestion():
    """Simple test that the suggestion can be built from a sample event response"""


# sports/backends/sportsdata/common:
@pytest.mark.asyncio
async def test_gamestatus():
    """Test the GameStatus enum"""
    assert GameStatus.parse("final") == GameStatus.Final
    assert GameStatus.parse("final - shoot out") == GameStatus.F_SO
    assert GameStatus.parse("F/OT") == GameStatus.F_OT
    assert GameStatus.parse("Banana") == GameStatus.Unknown

    assert GameStatus.Final.is_final()
    assert GameStatus.parse("scheduled").is_scheduled()
    assert GameStatus.parse("suspended").is_in_progress()
    assert GameStatus.F_OT.status_type() == GameStatus.Final
    assert GameStatus.parse("In Progress").status_type() == GameStatus.InProgress
    assert GameStatus.NotNecessary.as_str() == "Not Necessary"


# sports/backends/sportsdata/common/data.py
@pytest.mark.asyncio
async def test_sportdate():
    """Test the date handler and composer"""
    now = datetime.now(tz=timezone.utc)
    now_str = now.strftime("%Y-%b-%d")
    date = SportDate(instance=now)
    assert str(date) == now_str
    assert date == SportDate.parse(now_str)


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
    team = Team.from_data(
        team_data=team_data, term_filter=["La", "The", "fc"], team_ttl=ttl
    )
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
