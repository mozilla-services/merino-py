# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import pytest
from fastapi.testclient import TestClient

from merino.providers import BaseProvider
from tests.integration.api.v1.fake_providers import (
    HiddenProvider,
    NonsponsoredProvider,
    SponsoredProvider,
)


@pytest.mark.parametrize(
    "expected_response, providers",
    [
        ([], {}),
        (
            [
                {"id": "sponsored-provider", "availability": "enabled_by_default"},
            ],
            {
                "sponsored-provider": SponsoredProvider(enabled_by_default=True),
            },
        ),
        (
            [
                {"id": "sponsored-provider", "availability": "disabled_by_default"},
            ],
            {
                "sponsored-provider": SponsoredProvider(enabled_by_default=False),
            },
        ),
        (
            [
                {"id": "hidden-provider", "availability": "hidden"},
            ],
            {
                "hidden-provider": HiddenProvider(enabled_by_default=True),
            },
        ),
        (
            [
                {"id": "sponsored-provider", "availability": "enabled_by_default"},
                {"id": "nonsponsored-provider", "availability": "disabled_by_default"},
                {"id": "hidden-provider", "availability": "hidden"},
            ],
            {
                "sponsored-provider": SponsoredProvider(enabled_by_default=True),
                "nonsponsored-provider": NonsponsoredProvider(enabled_by_default=False),
                "hidden-provider": HiddenProvider(enabled_by_default=True),
            },
        ),
    ],
)
def test_providers(
    client: TestClient,
    expected_response: list[dict[str, str]],
    providers: dict[str, BaseProvider],
) -> None:
    """
    Tests that the response to the 'providers' endpoint is as expected when 0-to-many
    providers are registered with different availabilities
    """
    response = client.get("/api/v1/providers")

    assert response.status_code == 200
    assert response.json() == expected_response
