# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""WCS integration test fixtures."""

from collections.abc import Iterator

import pytest
from pytest_mock import MockerFixture

from merino.main import app
from merino.middleware import ScopeKey
from merino.middleware.geolocation import GeolocationMiddleware, Location
from merino.providers.wcs import get_provider as get_wcs_provider
from tests.wcs.factories import build_provider


@pytest.fixture(autouse=True)
def wcs_provider_override() -> Iterator[None]:
    """Serve deterministic WCS data without connecting to Redis."""
    provider = build_provider()
    app.dependency_overrides[get_wcs_provider] = lambda: provider
    yield
    del app.dependency_overrides[get_wcs_provider]


@pytest.fixture
def inject_us_location(mocker: MockerFixture) -> None:
    """Patch GeolocationMiddleware to inject a United States location into every HTTP request scope."""
    us_location = Location(country="US")

    async def patched_call(self: GeolocationMiddleware, scope, receive, send) -> None:
        if scope.get("type") == "http":
            scope[ScopeKey.GEOLOCATION] = us_location
        await self.app(scope, receive, send)

    mocker.patch.object(GeolocationMiddleware, "__call__", patched_call)
