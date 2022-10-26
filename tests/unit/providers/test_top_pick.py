# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
import os
from collections import defaultdict

import pytest
from fastapi import APIRouter, FastAPI

from merino.config import settings

# from merino.config import settings
from merino.providers.top_pick import Provider

app = FastAPI()
router = APIRouter()

top_pick_example = {
    "domains": {
        "items": [
            {
                "rank": 3,
                "domain": "mozilla",
                "title": "Mozilla",
                "url": "https://mozilla.org/en-US/",
                "icon": -1,
                "categories": {"items": []},
                "similars": ["mozzilla", "mozila"],
            }
        ]
    }
}


@pytest.fixture(name="top_pick")
def fixture_top_pick() -> Provider:
    """Return Top Pick Navigational Query Provider"""
    return Provider(app, "top_pick", False)


def test_enabled_by_default(top_pick: Provider) -> None:
    """Test for the enabled_by_default method."""

    assert top_pick.enabled_by_default is False


def test_hidden(top_pick: Provider) -> None:
    """Test for the hidden method."""

    assert top_pick.hidden() is False


def test_local_file_exists() -> None:
    """Test that the Top Picks Nav Query file exists locally"""
    assert os.path.exists(settings.providers.top_pick.top_pick_file_path) is True


def test_read_domain_list(top_pick: Provider) -> None:
    """Test that the JSON file containing the domain list can be processed"""
    with pytest.raises(FileNotFoundError):
        top_pick.read_domain_list("./wrongfile.json")
    domain_list = top_pick.read_domain_list(
        settings.providers.top_pick.top_pick_file_path
    )
    assert type(domain_list) == dict
    assert domain_list["domains"]["items"][0]["domain"] == "example"
    assert len(domain_list["domains"]["items"][1]["similars"]) == 5
    assert domain_list["domains"]["items"][2] == top_pick_example["domains"]["items"][0]


def test_build_index(top_pick: Provider) -> None:
    """Test constructing the primary and secondary indexes and suggestions"""
    domain_list = top_pick.read_domain_list(
        settings.providers.top_pick.top_pick_file_path
    )
    primary, secondary = top_pick.build_index(domain_list)
    primary_index = primary[0]
    primary_results = primary[1]
    secondary_index = secondary[0]
    secondary_results = secondary[1]
    assert type(primary[0]) == defaultdict
    assert type(primary_index) == defaultdict
    assert "exa" not in primary_index
    assert "exam" in primary_index
    assert "examp" in primary_index
    assert "exampl" in primary_index
    assert "example" in primary_index
    assert primary_index["mozilla"] == [2]

    assert type(primary[1]) == list
    assert type(primary_results) == list
    assert len(primary_results) == 3
    assert primary_results[0]["domain"] == "example"
    assert primary_results[1]["url"] == "https://firefox.com"

    assert primary_results[primary_index["exam"][0]]["domain"] == "example"
    assert primary_results[primary_index["firefo"][0]]["url"] == "https://firefox.com"

    for key, value in primary_index.items():
        assert key in primary_results[primary_index[key][0]]["domain"]

    assert type(secondary[0]) == defaultdict
    assert type(secondary_index) == defaultdict
    assert "exa" not in secondary_index
    assert secondary_results[secondary_index["exam"][0]]["domain"] == "example"
    assert (
        secondary_results[secondary_index["firefo"][0]]["url"] == "https://firefox.com"
    )


def test_build_indeces(top_pick: Provider) -> None:
    primary, secondary = top_pick.build_indices()
    primary_index = primary[0]
    primary_results = primary[1]
    assert type(primary[0]) == defaultdict
    assert type(primary_index) == defaultdict
    assert "exa" not in primary_index
    assert "exam" in primary_index
    assert "examp" in primary_index
    assert "exampl" in primary_index
    assert "example" in primary_index
    # assert primary_index["mozilla"] == [2]

    assert type(primary[1]) == list
    assert type(primary_results) == list
    assert len(primary_results) == 3
    assert primary_results[0]["domain"] == "example"
    assert primary_results[1]["url"] == "https://firefox.com"


@pytest.mark.asyncio
async def test_initialize(top_pick: Provider) -> None:
    await top_pick.initialize()
    assert type(top_pick.primary_index) == defaultdict
    assert type(top_pick.secondary_index) == defaultdict
    assert type(top_pick.primary_results) == list
    assert type(top_pick.secondary_results) == list


@pytest.mark.asyncio
async def test_query(top_pick: Provider) -> None:
    """Test for the query method of the Top Pick provider."""
    await top_pick.initialize()

    res = await top_pick.query("am")
    assert res == []
