# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the test_block_list.py utility module."""
import pytest

from merino.config import settings
from merino.utils.block_list import read_block_list


@pytest.fixture(name="expected_block_list")
def fixture_expected_block_list() -> set[str]:
    """Return an expected block list."""
    return {"Unsafe_Content", "Blocked"}


def test_read_block_list(expected_block_list: set[str]) -> None:
    """Test that read_block_list method returns a block list"""
    block_list = read_block_list(settings.providers.wikipedia.block_list_path)

    assert block_list == expected_block_list
