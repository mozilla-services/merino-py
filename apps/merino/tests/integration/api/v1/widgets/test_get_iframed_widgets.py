# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Integration tests for the /api/v1/widgets/iframed endpoint."""

from fastapi.testclient import TestClient

from merino.providers.widgets.iframed.provider import Provider as IframedWidgetsProvider

WIDGETS_URL = "/api/v1/widgets/iframed"


def test_returns_widgets(
    client: TestClient, iframed_widgets_provider: IframedWidgetsProvider
) -> None:
    """Serves the hard-coded widgets response, passing through the default locale."""
    response = client.get(WIDGETS_URL)

    assert response.status_code == 200

    data = response.json()

    assert data["date_utc"] is not None
    assert data["locale"] == "en-US"
    assert len(data["widgets"]) == 5


def test_returns_empty_list_of_widgets_when_provider_disabled(
    client: TestClient, iframed_widgets_provider: IframedWidgetsProvider
) -> None:
    """Returns an empty list of widgets when the provider is disabled."""
    iframed_widgets_provider._enabled = False

    response = client.get(WIDGETS_URL)

    data = response.json()

    assert data["date_utc"] is not None
    assert data["locale"] == "en-US"
    assert len(data["widgets"]) == 0
