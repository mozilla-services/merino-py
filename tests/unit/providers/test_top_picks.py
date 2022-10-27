# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
import os
from collections import defaultdict

import pytest
from fastapi import APIRouter, FastAPI

from merino.config import settings

# from merino.config import settings
from merino.providers.top_picks import Provider, Suggestion

app = FastAPI()
router = APIRouter()

top_picks_example = {
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


@pytest.fixture(name="top_picks")
def fixture_top_pick() -> Provider:
    """Return Top Pick Navigational Query Provider"""
    return Provider(app, "top_picks", False)


def test_enabled_by_default(top_picks: Provider) -> None:
    """Test for the enabled_by_default method."""

    assert top_picks.enabled_by_default is False


def test_hidden(top_picks: Provider) -> None:
    """Test for the hidden method."""

    assert top_picks.hidden() is False


def test_local_file_exists() -> None:
    """Test that the Top Picks Nav Query file exists locally"""
    assert os.path.exists(settings.providers.top_picks.top_picks_file_path) is True


def test_read_domain_list(top_picks: Provider) -> None:
    """Test that the JSON file containing the domain list can be processed"""
    with pytest.raises(FileNotFoundError):
        top_picks.read_domain_list("./wrongfile.json")
    domain_list = top_picks.read_domain_list(
        settings.providers.top_picks.top_picks_file_path
    )
    assert type(domain_list) == dict
    assert domain_list["domains"][0]["domain"] == "example"
    assert len(domain_list["domains"][1]["similars"]) == 5


def test_build_index(top_picks: Provider) -> None:
    """Test constructing the primary and secondary indexes and suggestions"""
    domain_list = top_picks.read_domain_list(
        settings.providers.top_picks.top_picks_file_path
    )
    source_dict = top_picks.build_index(domain_list)

    assert "exa" not in source_dict["primary_index"]
    assert "exam" in source_dict["primary_index"]
    assert "examp" in source_dict["primary_index"]
    assert "exampl" in source_dict["primary_index"]
    assert "example" in source_dict["primary_index"]

    # Assertions to ensure any domains short of query limit
    # return empty collections
    short_domain_list = {
        "domains": [
            {
                "rank": 1,
                "title": "aaa",
                "domain": "aaa",
                "url": "https://aaa.com",
                "icon": "",
                "categories": ["web-browser"],
                "similars": [],
            },
        ]
    }

    short_domain_dict = top_picks.build_index(short_domain_list)

    assert len(short_domain_dict["results"]) == 0
    assert short_domain_dict["results"] == []
    assert short_domain_dict["primary_index"] == {}


def test_build_indeces(top_picks: Provider) -> None:
    """Test to build indexes and result data structures"""
    source_dict = top_picks.build_indices()
    source_dict["primary_index"]
    source_dict["secondary_index"]
    source_dict["results"]


@pytest.mark.asyncio
async def test_initialize(top_picks: Provider) -> None:
    """Test initialization of top pick provider"""
    await top_picks.initialize()
    assert type(top_picks.primary_index) == defaultdict
    assert type(top_picks.secondary_index) == defaultdict
    assert type(top_picks.results) == list


@pytest.mark.asyncio
async def test_initialize_exception(top_picks: Provider) -> None:
    """Test that proper exception is thrown if initialization is unsuccessful"""
    with pytest.raises(Exception):
        top_picks.initialize(0)


@pytest.mark.asyncio
async def test_query(top_picks: Provider) -> None:
    """Test for the query method of the Top Pick provider."""

    await top_picks.initialize()
    assert await top_picks.query("am") == []
    assert await top_picks.query("https://") == []
    assert await top_picks.query("supercalifragilisticexpialidocious") == []

    res = await top_picks.query("example")
    assert (
        res
        == [
            Suggestion(
                block_id=0,
                rank=1,
                title="Example",
                domain="example",
                url="https://example.com",
                provider="top_picks",
                is_top_pick=True,
                is_sponsored=False,
                icon="",
                score=settings.providers.top_picks.score,
            )
        ][0]
    )

    res = await top_picks.query("exxamp")
    assert (
        res
        == [
            Suggestion(
                block_id=0,
                rank=1,
                title="Example",
                domain="example",
                url="https://example.com",
                provider="top_picks",
                is_top_pick=True,
                is_sponsored=False,
                icon="",
                score=settings.providers.top_picks.score,
            )
        ][0]
    )
