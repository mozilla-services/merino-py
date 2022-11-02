# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import pytest
from fastapi.testclient import TestClient

from merino.providers import BaseProvider
from tests.integration.api.v1.models import NonsponsoredProvider, SponsoredProvider
from tests.integration.api.v1.types import (
    SetupProvidersFixture,
    TeardownProvidersFixture,
)


@pytest.fixture(autouse=True)
def inject_providers(
    setup_providers: SetupProvidersFixture, teardown_providers: TeardownProvidersFixture
):
    providers: dict[str, BaseProvider] = {
        "sponsored-provider": SponsoredProvider(enabled_by_default=True),
        "nonsponsored-provider": NonsponsoredProvider(enabled_by_default=True),
    }
    setup_providers(providers)
    yield
    teardown_providers()


def test_providers(client: TestClient):
    expected_providers = {"sponsored-provider", "nonsponsored-provider"}

    response = client.get("/api/v1/providers")

    assert response.status_code == 200
    providers = response.json()
    assert len(providers) == 2
    assert set([provider["id"] for provider in providers]) == expected_providers
