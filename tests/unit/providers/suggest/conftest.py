# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Shared test fixtures for suggest provider unit tests."""

import pytest
from unittest.mock import AsyncMock


@pytest.fixture(name="logo_provider_mock")
def fixture_logo_provider_mock() -> AsyncMock:
    """Return a mock logos provider with get_logo_url returning None."""
    return AsyncMock(get_logo_url=AsyncMock(return_value=None))
