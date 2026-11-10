# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the Framed Widgets backend."""

import pytest

from google.cloud.storage import Client
from pydantic import HttpUrl
from unittest.mock import MagicMock

from merino.providers.widgets.iframed.backends.framed import FramedWidgetsBackend
from merino.providers.widgets.iframed.backends.protocol import FramedWidgetGCS


@pytest.fixture(name="gcs_client_mock")
def fixture_gcs_client_mock() -> Client:
    """Return a mock GCS Client."""
    return MagicMock(spec=Client)


@pytest.fixture(name="backend")
def fixture_backend(
    gcs_client_mock: Client,
    statsd_mock,
) -> FramedWidgetsBackend:
    """Return a FramedBackend instance for testing."""
    return FramedWidgetsBackend(gcs_client=gcs_client_mock, metrics_client=statsd_mock)


class TestFetch:
    """Tests against fetch_manifest_json"""

    @pytest.mark.asyncio
    async def test_returns_widgets(self, backend: FramedWidgetsBackend) -> None:
        """Test fetch."""
        backend.widgets_manifest = [
            FramedWidgetGCS(
                bucket_name="test bucket 1",
                cdn_host="https://test-bucket-1",
                enabled=True,
                id="test1",
                vendor="mozilla",
            ),
            FramedWidgetGCS(
                bucket_name="test bucket 2",
                cdn_host="https://test-bucket-2",
                enabled=True,
                id="test2",
                vendor="mozilla",
            ),
        ]

        result = await backend.fetch()

        # we should have an entry for each widget in the manifest
        assert len(result) == 2


class TestBuildSemverUrl:
    """Test the build_semver_url helper."""

    def test_build_url(self, backend: FramedWidgetsBackend):
        """Verify the URL is built as expected."""
        result = backend.build_semver_url(
            cdn_host="stage-widgets-test.merino.nonprod.webservices.mozgcp.net", semver="1.0.test"
        )

        assert result == HttpUrl(
            "https://stage-widgets-test.merino.nonprod.webservices.mozgcp.net/1.0.test/index.html"
        )
