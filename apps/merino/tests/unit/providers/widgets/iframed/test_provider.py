# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the iframed widget provider module."""

import pytest

from merino.providers.widgets.iframed.provider import Provider as IframedWidgetProvider


@pytest.fixture(name="provider")
def fixture_provider(statsd_mock) -> IframedWidgetProvider:
    """Return a Provider instance for testing."""
    return IframedWidgetProvider(
        metrics_client=statsd_mock,
        name="iframed Widget Provider",
        enabled=True,
    )


class TestGetWidgets:
    """Tests against get_widgets"""

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_provider_disabled(
        self, provider: IframedWidgetProvider
    ) -> None:
        """Test that no widgets are returned when the provider is disabled."""
        provider._enabled = False

        response = await provider.get_widgets(locale="en-US")

        assert response.widgets is not None
        assert len(response.widgets) == 0

    @pytest.mark.asyncio
    async def test_returns_hard_coded_widgets_list(self, provider: IframedWidgetProvider) -> None:
        """Test that get_widgets returns the hard-coded list."""
        response = await provider.get_widgets(locale="en-US")

        assert response.widgets is not None
        assert len(response.widgets) == 5

    @pytest.mark.asyncio
    async def test_returns_stage_widgets_for_stage_env(
        self, provider: IframedWidgetProvider, force_env
    ) -> None:
        """Test that get_widgets returns the hard-coded staging list."""
        force_env("stage")

        response = await provider.get_widgets(locale="en-US")

        assert response.widgets is not None
        assert len(response.widgets) == 5

        for widget in response.widgets:
            assert ".nonprod.webservices.mozgcp.net" in str(widget.url.host)

    @pytest.mark.asyncio
    async def test_returns_prod_widgets_for_prod_env(
        self, provider: IframedWidgetProvider, force_env
    ) -> None:
        """Test that get_widgets returns the hard-coded production list."""
        force_env("production")

        response = await provider.get_widgets(locale="en-US")

        assert response.widgets is not None
        assert len(response.widgets) == 5

        for widget in response.widgets:
            assert ".prod.webservices.mozgcp.net" in str(widget.url.host)
