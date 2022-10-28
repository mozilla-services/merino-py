# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
import os

import pytest
from fastapi import APIRouter, FastAPI

from merino.config import settings
from merino.providers.top_picks import Provider, Suggestion

app = FastAPI()
router = APIRouter()

QUERY_CHAR_LIMIT: int = settings.providers.top_picks.query_char_limit

top_picks_example = {
    "domains": [
        {
            "title": "Mozilla",
            "url": "https://mozilla.org/en-US/",
            "icon": "",
            "categories": ["web-browser"],
            "similars": ["mozzilla", "mozila"],
        },
    ]
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
    assert os.path.exists(settings.providers.top_picks.top_picks_file_path)


def test_local_file_not_found(mocker) -> None:
    """Test that the Top Picks Nav Query file exists locally"""
    mocker.patch("os.path.exists", return_value=False)
    assert not os.path.exists(settings.providers.top_picks.top_picks_file_path)


def test_read_domain_list(top_picks: Provider) -> None:
    """Test that the JSON file containing the domain list can be processed"""
    domain_list = top_picks.read_domain_list(
        settings.providers.top_picks.top_picks_file_path
    )
    assert domain_list["domains"][0]["domain"] == "example"
    assert len(domain_list["domains"][1]["similars"]) == 5


def test_read_domain_list_exception(top_picks: Provider) -> None:
    """Test that the JSON file containing the domain list can be processed"""
    with pytest.raises(FileNotFoundError):
        top_picks.read_domain_list("./wrongfile.json")


def test_build_indexes(top_picks: Provider) -> None:
    """Test constructing the primary and secondary indexes and suggestions"""
    domain_list = top_picks.read_domain_list(
        settings.providers.top_picks.top_picks_file_path
    )
    result = top_picks.build_index(domain_list)
    primary_index = result["primary_index"]
    secondary_index = result["secondary_index"]
    results = result["results"]
    # primary

    example_query = "example"
    for chars in range(QUERY_CHAR_LIMIT, len("example_query") + 1):
        assert example_query[:chars] in result["primary_index"]
        assert results[primary_index[example_query[:chars]][0]]
    #  secondary
    example_query = "fiirefox"
    for chars in range(QUERY_CHAR_LIMIT, len("example_query") + 1):
        assert example_query[:chars] in result["secondary_index"]
        assert results[secondary_index[example_query[:chars]][0]]


def test_build_indeces(top_picks: Provider) -> None:
    """Test to build indexes and result data structures"""
    source_dict = top_picks.build_indices()
    assert source_dict["primary_index"]
    assert source_dict["secondary_index"]
    assert source_dict["results"]
    assert source_dict["index_char_range"]


@pytest.mark.asyncio
async def test_initialize(top_picks: Provider) -> None:
    """Test initialization of top pick provider"""
    await top_picks.initialize()
    assert top_picks.primary_index
    assert top_picks.secondary_index
    assert top_picks.results


@pytest.mark.asyncio
async def test_initialize_exception(top_picks: Provider, mocker) -> None:
    """Test that proper exception is thrown if initialization is unsuccessful"""
    mocker.patch.object(top_picks, "initialize", side_effect=Exception)
    with pytest.raises(Exception):
        await top_picks.initialize()


@pytest.mark.asyncio
async def test_query(top_picks: Provider) -> None:
    """Test for the query method of the Top Pick provider."""

    await top_picks.initialize()
    assert await top_picks.query("am") == []
    assert await top_picks.query("https://") == []
    assert await top_picks.query("supercalifragilisticexpialidocious") == []

    res = await top_picks.query("example")
    assert res == [
        Suggestion(
            block_id=0,
            title="Example",
            url="https://example.com",
            provider="top_picks",
            is_top_pick=True,
            is_sponsored=False,
            icon="",
            score=settings.providers.top_picks.score,
        )
    ]

    res = await top_picks.query("exxamp")
    assert res == [
        Suggestion(
            block_id=0,
            title="Example",
            url="https://example.com",
            provider="top_picks",
            is_top_pick=True,
            is_sponsored=False,
            icon="",
            score=settings.providers.top_picks.score,
        )
    ]
