# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import os

import pytest
from fastapi import APIRouter, FastAPI

from merino.config import settings

# from merino.config import settings
from merino.providers.top_pick import Provider

app = FastAPI()
router = APIRouter()


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


def test_local_file_exists(top_pick: Provider) -> None:
    """Test that the Top Picks Nav Query file exists locally"""
    assert os.path.exists(settings.providers.top_pick.top_pick_file_path) is True
