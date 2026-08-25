# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Integration tests for the Merino v1 providers API endpoint."""

import pytest
from fastapi.testclient import TestClient

from merino.providers.suggest import BaseProvider
from tests.integration.api.v1.fake_providers import FakeProviderFactory


@pytest.mark.parametrize(
    ["expected_response", "providers"],
    [
        ([], {}),
        (
            [
                {"id": "sponsored", "availability": "enabled_by_default"},
            ],
            {
                "sponsored": FakeProviderFactory.sponsored(enabled_by_default=True),
            },
        ),
        (
            [
                {"id": "sponsored", "availability": "disabled_by_default"},
            ],
            {
                "sponsored": FakeProviderFactory.sponsored(enabled_by_default=False),
            },
        ),
        (
            [
                {"id": "hidden-provider", "availability": "hidden"},
            ],
            {
                "hidden-provider": FakeProviderFactory.hidden(enabled_by_default=True),
            },
        ),
        (
            [
                {"id": "sponsored", "availability": "enabled_by_default"},
                {"id": "nonsponsored", "availability": "disabled_by_default"},
                {"id": "hidden-provider", "availability": "hidden"},
            ],
            {
                "sponsored": FakeProviderFactory.sponsored(enabled_by_default=True),
                "nonsponsored": FakeProviderFactory.nonsponsored(enabled_by_default=False),
                "hidden-provider": FakeProviderFactory.hidden(enabled_by_default=True),
            },
        ),
    ],
    ids=[
        "no-providers",
        "one-provider-enabled_by_default",
        "one-provider-disabled_by_default",
        "one-provider-hidden",
        "three-providers-all-availabilities",
    ],
)
def test_providers(
    client: TestClient,
    expected_response: list[dict[str, str]],
    providers: dict[str, BaseProvider],
) -> None:
    """Test that the response to the 'providers' endpoint is as expected when 0-to-many
    providers are registered with different availabilities
    """
    response = client.get("/api/v1/providers")

    assert response.status_code == 200
    assert response.json() == expected_response


@pytest.mark.parametrize(
    [
        "expected_response",
        "providers",
    ],
    [
        (
            [],
            {
                "disabled_provider": FakeProviderFactory.disabled_provider(
                    enabled_by_default=True
                ),
            },
        ),
    ],
    ids=[
        "disabled_provider",
    ],
)
def test_disabled_providers_setting(
    client: TestClient,
    expected_response: list[dict[str, str]],
    providers: dict[str, BaseProvider],
) -> None:
    """Test that the disabled_providers setting behaves as expected when
    querying the providers endpoint.
    """
    response = client.get("/api/v1/providers")

    assert response.status_code == 200
    assert response.json() == expected_response
