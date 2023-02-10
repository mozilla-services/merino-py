# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the Top Picks backend module."""
import os
from typing import Any

import pytest

from merino.config import settings
from merino.providers.top_picks.backends.top_picks import (
    TopPicksBackend,
    TopPicksData,
    TopPicksError,
)


@pytest.fixture(name="top_picks_parameters")
def fixture_top_picks_parameters() -> dict[str, Any]:
    """Create a Top Picks object for test."""
    return {
        "top_picks_file_path": settings.providers.top_picks.top_picks_file_path,
        "query_char_limit": settings.providers.top_picks.query_char_limit,
        "firefox_char_limit": settings.providers.top_picks.firefox_char_limit,
    }


@pytest.fixture(name="top_picks")
def fixture_top_picks(top_picks_parameters: dict[str, Any]) -> TopPicksBackend:
    """Create a Top Picks object for test."""
    return TopPicksBackend(**top_picks_parameters)


def test_init_failure_no_domain_file(
    top_picks_parameters: dict[str, Any]
) -> TopPicksBackend:
    """Test exception handling for the __init__() method when no domain file provided."""
    top_picks_parameters["top_picks_file_path"] = None
    with pytest.raises(ValueError):
        TopPicksBackend(**top_picks_parameters)


def test_local_file_exists() -> None:
    """Test that the Top Picks Nav Query file exists locally"""
    assert os.path.exists(settings.providers.top_picks.top_picks_file_path)


def test_read_domain_list(top_picks: TopPicksBackend) -> None:
    """Test that the JSON file containing the domain list can be processed"""
    domain_list = top_picks.read_domain_list(
        settings.providers.top_picks.top_picks_file_path
    )
    assert domain_list["domains"][0]["domain"] == "example"
    assert len(domain_list["domains"][1]["similars"]) == 5


def test_read_domain_list_os_error(top_picks: TopPicksBackend) -> None:
    """Test that read domain fails and raises exception with invalid file path."""
    with pytest.raises(TopPicksError):
        top_picks.read_domain_list("./wrongfile.json")


@pytest.mark.asyncio
async def test_fetch(top_picks: TopPicksBackend, top_picks_data: TopPicksData) -> None:
    """Test the fetch method returns TopPickData."""
    result = await top_picks.fetch()
    assert result == top_picks_data
