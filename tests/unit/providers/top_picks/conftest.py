# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Module for test configurations for the Top Picks provider unit test directory."""
from typing import Any

import pytest
from pytest_mock import MockerFixture

from merino.config import settings
from merino.providers.top_picks.backends.protocol import TopPicksBackend, TopPicksData
from merino.providers.top_picks.provider import Provider

config = settings.providers.top_picks


@pytest.fixture(name="top_picks_data")
def fixture_top_picks_data() -> TopPicksData:
    """Define Top Picks backend suggestion content for test."""
    return TopPicksData(
        primary_index={
            "exam": [0],
            "examp": [0],
            "exampl": [0],
            "example": [0],
            "fire": [1],
            "firef": [1],
            "firefo": [1],
            "firefox": [1],
            "mozi": [2],
            "mozil": [2],
            "mozill": [2],
            "mozilla": [2],
        },
        secondary_index={
            "exxa": [0],
            "exxam": [0],
            "exxamp": [0],
            "exxampl": [0],
            "exxample": [0],
            "exam": [0],
            "examp": [0],
            "exampp": [0],
            "examppl": [0],
            "exampple": [0],
            "eexa": [0],
            "eexam": [0],
            "eexamp": [0],
            "eexampl": [0],
            "eexample": [0],
            "fire": [1, 1, 1],
            "firef": [1, 1],
            "firefo": [1, 1],
            "firefox": [1, 1],
            "firefoxx": [1],
            "foye": [1],
            "foyer": [1],
            "foyerf": [1],
            "foyerfo": [1],
            "foyerfox": [1],
            "fiir": [1],
            "fiire": [1],
            "fiiref": [1],
            "fiirefo": [1],
            "fiirefox": [1],
            "fires": [1],
            "firesf": [1],
            "firesfo": [1],
            "firesfox": [1],
            "firefoxe": [1],
            "firefoxes": [1],
            "mozz": [2],
            "mozzi": [2],
            "mozzil": [2],
            "mozzill": [2],
            "mozzilla": [2],
            "mozi": [2],
            "mozil": [2],
            "mozila": [2],
            "acbc": [3],
            "aecb": [3],
            "aecbc": [3],
        },
        short_domain_index={"ab": [3, 3], "abc": [3], "aa": [3], "ac": [3], "acb": [3]},
        results=[
            {
                "block_id": 0,
                "title": "Example",
                "url": "https://example.com",
                "provider": "top_picks",
                "is_top_pick": True,
                "is_sponsored": False,
                "icon": "",
                "score": 0.25,
            },
            {
                "block_id": 0,
                "title": "Firefox",
                "url": "https://firefox.com",
                "provider": "top_picks",
                "is_top_pick": True,
                "is_sponsored": False,
                "icon": "",
                "score": 0.25,
            },
            {
                "block_id": 0,
                "title": "Mozilla",
                "url": "https://mozilla.org/en-US/",
                "provider": "top_picks",
                "is_top_pick": True,
                "is_sponsored": False,
                "icon": "",
                "score": 0.25,
            },
            {
                "block_id": 0,
                "title": "Abc",
                "url": "https://abc.test",
                "provider": "top_picks",
                "is_top_pick": True,
                "is_sponsored": False,
                "icon": "",
                "score": 0.25,
            },
        ],
        index_char_range=(4, 7),
        query_char_limit=4,
        firefox_char_limit=2,
    )


@pytest.fixture(name="top_picks_parameters")
def fixture_top_picks_parameters() -> dict[str, Any]:
    """Define Top Pick provider parameters for test."""
    return {"name": "top_picks", "enabled_by_default": config.enabled_by_default}


@pytest.fixture(name="backend_mock")
def fixture_backend_mock(mocker: MockerFixture, top_picks_data: TopPicksData) -> Any:
    """Create a Top Pick backend mock object for test."""
    backend_mock: Any = mocker.AsyncMock(spec=TopPicksBackend)
    backend_mock.fetch.return_value = top_picks_data
    return backend_mock


@pytest.fixture(name="top_picks")
def fixture_top_picks(
    backend_mock: Any, top_picks_parameters: dict[str, Any]
) -> Provider:
    """Create Top Pick Provider for test."""
    return Provider(backend=backend_mock, **top_picks_parameters)
