# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Integration tests for the Merino v1 suggest API endpoint configured with the
Top Picks provider.
"""
from typing import Any

import pytest
from pytest_mock import MockerFixture

from merino.config import settings
from merino.providers.top_picks.backends.top_picks import TopPicksBackend
from merino.providers.top_picks.provider import Provider as TopPicksProvider
from tests.integration.api.v1.types import Providers


@pytest.fixture(name="backend_mock")
def fixture_backend_mock(mocker: MockerFixture) -> Any:
    """Create a TopPicksBackend mock object for test."""
    return mocker.AsyncMock(spec=TopPicksBackend)


@pytest.fixture(name="providers")
def fixture_providers(backend_mock: Any) -> Providers:
    """Define providers for this module which are injected automatically."""
    return {
        "top_picks": TopPicksProvider(
            backend=backend_mock,
            name="top_picks",
            enabled_by_default=settings.providers.top_picks.enabled_by_default,
        )
    }
