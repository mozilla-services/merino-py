# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Test configurations for the widget API endpoint tests."""

from typing import Any

import pytest

from merino.main import app
from merino.providers.widgets import get_iframed_widgets_provider, get_wrexham_provider
from merino.providers.widgets.wrexham.provider import WrexhamProvider
from merino.providers.widgets.iframed.provider import Provider as IframedWidgetsProvider


@pytest.fixture(name="wrexham_provider")
def fixture_wrexham_provider() -> WrexhamProvider:
    """Create a Wrexham provider that serves mock data."""
    return WrexhamProvider(mock_data_enabled=True)


@pytest.fixture(name="inject_wrexham_provider", autouse=True)
def fixture_inject_wrexham_provider(wrexham_provider: WrexhamProvider):
    """Inject the Wrexham provider into the app for testing."""

    def get_test_wrexham_provider() -> WrexhamProvider:
        return wrexham_provider

    app.dependency_overrides[get_wrexham_provider] = get_test_wrexham_provider
    yield
    del app.dependency_overrides[get_wrexham_provider]


@pytest.fixture(name="iframed_widgets_provider")
def fixture_iframed_widgets_provider(statsd_mock: Any) -> IframedWidgetsProvider:
    """Create an iframed widgets provider."""
    return IframedWidgetsProvider(
        metrics_client=statsd_mock,
        name="test_iframed_widgets",
        enabled=True,
    )


@pytest.fixture(name="inject_iframed_widgets_provider", autouse=True)
def fixture_inject_iframed_widgets_provider(iframed_widgets_provider: IframedWidgetsProvider):
    """Inject the iframed widgets provider into the app for testing."""

    def get_test_iframed_widgets_provider() -> IframedWidgetsProvider:
        return iframed_widgets_provider

    app.dependency_overrides[get_iframed_widgets_provider] = get_test_iframed_widgets_provider
    yield
    del app.dependency_overrides[get_iframed_widgets_provider]
