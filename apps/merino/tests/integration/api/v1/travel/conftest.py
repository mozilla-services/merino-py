# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Test configurations for the travel API endpoint tests."""

from typing import Any

import pytest
from pytest_mock import MockerFixture

from merino.main import app
from merino.providers.travel import get_travel_provider
from merino.providers.travel.kayak.backends.protocol import TravelBackend
from merino.providers.travel.kayak.provider import Provider as TravelProvider


@pytest.fixture(name="backend_mock")
def fixture_backend_mock(mocker: MockerFixture) -> Any:
    """Create a TravelBackend mock object for test."""
    backend_mock = mocker.AsyncMock(spec=TravelBackend)
    backend_mock.get_listings.return_value = []
    return backend_mock


@pytest.fixture(name="travel_provider")
def fixture_travel_provider(backend_mock: Any, statsd_mock: Any) -> TravelProvider:
    """Create a travel provider with a mocked backend."""
    return TravelProvider(
        backend=backend_mock,
        metrics_client=statsd_mock,
        name="test_travel",
        enabled=True,
    )


@pytest.fixture(name="inject_travel_provider", autouse=True)
def fixture_inject_travel_provider(travel_provider: TravelProvider):
    """Inject the travel provider into the app for testing."""

    def get_test_travel_provider() -> TravelProvider:
        return travel_provider

    app.dependency_overrides[get_travel_provider] = get_test_travel_provider
    yield
    del app.dependency_overrides[get_travel_provider]
