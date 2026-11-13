# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Integration tests for the /api/v1/widgets/framed endpoint."""

from fastapi.testclient import TestClient
from pydantic import HttpUrl

from merino.providers.widgets.iframed.provider import Provider as FramedWidgetsProvider
from merino.providers.widgets.iframed.backends.protocol import FramedWidgetResponse

WIDGETS_URL = "/api/v1/widgets/framed"


def test_returns_widgets(
    client: TestClient, framed_widgets_provider: FramedWidgetsProvider
) -> None:
    """Serves the hard-coded widgets response, passing through the default locale."""
    widgets = [
        FramedWidgetResponse(
            enabled=True, id="test1", vendor="mozilla", url=HttpUrl("https://mozilla.org/")
        ),
        FramedWidgetResponse(
            enabled=True, id="test2", vendor="external", url=HttpUrl("https://vendor.com/")
        ),
    ]

    framed_widgets_provider._cron_enabled = True
    framed_widgets_provider._inject_particle = False

    framed_widgets_provider.widgets_response = widgets

    response = client.get(WIDGETS_URL)

    assert response.status_code == 200

    data = response.json()

    assert data["date_utc"] is not None
    assert data["locale"] == "en-US"
    assert len(data["widgets"]) == 2


def test_returns_empty_list_of_widgets_when_provider_disabled(
    client: TestClient, framed_widgets_provider: FramedWidgetsProvider
) -> None:
    """Returns an empty list of widgets when the provider is disabled."""
    framed_widgets_provider._enabled = False

    response = client.get(WIDGETS_URL)

    data = response.json()

    assert data["date_utc"] is not None
    assert data["locale"] == "en-US"
    assert len(data["widgets"]) == 0
