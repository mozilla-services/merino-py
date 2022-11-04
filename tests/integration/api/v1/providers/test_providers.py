# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import pytest
from fastapi.testclient import TestClient

from tests.integration.api.v1.models import NonsponsoredProvider, SponsoredProvider
from tests.integration.api.v1.types import Providers


@pytest.fixture(name="providers")
def fixture_providers() -> Providers:
    """Define providers for this module which are injected automatically."""
    return {
        "sponsored-provider": SponsoredProvider(enabled_by_default=True),
        "nonsponsored-provider": NonsponsoredProvider(enabled_by_default=True),
    }


def test_providers(client: TestClient):
    expected_providers = {"sponsored-provider", "nonsponsored-provider"}

    response = client.get("/api/v1/providers")

    assert response.status_code == 200
    providers = response.json()
    assert len(providers) == 2
    assert set([provider["id"] for provider in providers]) == expected_providers
