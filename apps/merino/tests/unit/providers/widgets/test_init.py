# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the __init__ widget provider module."""

from datetime import timedelta
from unittest.mock import patch
from unittest.mock import AsyncMock, Mock

import pytest

import merino.providers.widgets as widgets
from merino.providers.widgets import (
    get_framed_widgets_provider,
    get_travel_provider,
    get_wrexham_provider,
    init_providers,
    shutdown_providers,
)
from merino.providers.widgets.iframed.provider import Provider as FramedWidgetProvider
from merino.providers.widgets.travel.kayak.provider import Provider as TravelProvider
from merino.providers.widgets.wrexham.provider import WrexhamProvider


class TestWrexhamProvider:
    """Test wrexham provider."""

    @pytest.mark.asyncio
    async def test_init_providers_creates_a_store_with_the_configured_expiry_times(self) -> None:
        """Gives the provider a store using the configured Redis expiry times."""
        await init_providers()

        store = get_wrexham_provider().store

        assert store.fixtures_ttl == timedelta(hours=1)
        assert store.live_matches_ttl == timedelta(minutes=5)
        assert store.standings_ttl == timedelta(hours=1)

    @pytest.mark.asyncio
    async def test_get_wrexham_provider_initialized(self) -> None:
        """Returns the provider instance after init_providers is called."""
        await init_providers()

        assert isinstance(get_wrexham_provider(), WrexhamProvider)

    def test_get_wrexham_provider_not_initialized(self) -> None:
        """Raises ValueError when the provider hasn't been initialized."""
        with patch("merino.providers.widgets._wrexham_provider", None):
            with pytest.raises(
                ValueError, match="Wrexham widget provider has not been initialized."
            ):
                get_wrexham_provider()

    @pytest.mark.asyncio
    async def test_shutdown_providers_shuts_down_and_resets(self) -> None:
        """Shuts down the Wrexham provider and clears module state."""
        await init_providers()
        provider = widgets._wrexham_provider
        assert provider is not None

        with patch.object(provider, "shutdown") as shutdown:
            await shutdown_providers()

        shutdown.assert_awaited_once()
        assert widgets._wrexham_provider is None
        with pytest.raises(ValueError, match="Wrexham widget provider has not been initialized."):
            get_wrexham_provider()

    @pytest.mark.asyncio
    async def test_shutdown_providers_when_not_initialized(self) -> None:
        """Does nothing when no provider has been initialized."""
        with patch("merino.providers.widgets._wrexham_provider", None):
            await shutdown_providers()


class TestTravelProvider:
    """Test the Travel provider."""

    @pytest.mark.asyncio
    async def test_init_providers_creates_travel_provider(self) -> None:
        """Initializes the travel provider with a Kayak backend built from settings."""
        with (
            patch("merino.providers.widgets._travel_enabled", True),
            patch("merino.providers.widgets._kayak_api_key", "mock_api_key"),
            patch("merino.providers.widgets._kayak_url_base", "mock_url_base"),
            patch(
                "merino.providers.widgets._kayak_url_autocomplete_path",
                "mock_url_autocomplete_path",
            ),
            patch("merino.providers.widgets.create_http_client") as mock_create_http_client,
            patch("merino.providers.widgets.get_metrics_client") as mock_get_metrics_client,
            patch("merino.providers.widgets.KayakBackend") as mock_kayak_backend,
        ):
            mock_http_client_instance = Mock(name="mock_http_client")
            mock_create_http_client.return_value = mock_http_client_instance

            mock_metrics_client_instance = Mock(name="mock_metrics_client")
            mock_get_metrics_client.return_value = mock_metrics_client_instance

            mock_kayak_backend_instance = Mock(name="mock_kayak_backend")
            mock_kayak_backend.return_value = mock_kayak_backend_instance

            await init_providers()

            travel_provider = widgets._travel_provider

            assert isinstance(travel_provider, TravelProvider)
            assert travel_provider.name == "Travel Provider"
            assert travel_provider.backend == mock_kayak_backend_instance
            assert travel_provider.metrics_client == mock_metrics_client_instance

            mock_kayak_backend.assert_called_once_with(
                api_key="mock_api_key",
                http_client=mock_http_client_instance,
                url_base="mock_url_base",
                url_autocomplete_path="mock_url_autocomplete_path",
                metrics_client=mock_metrics_client_instance,
            )

    @pytest.mark.asyncio
    async def test_get_travel_provider_initialized(self) -> None:
        """Verify get_travel_provider returns class instance after init_providers call."""
        await init_providers()

        assert isinstance(get_travel_provider(), TravelProvider)

    def test_get_travel_provider_not_initialized(self) -> None:
        """Verify that get_travel_provider raises ValueError when _travel_provider is not initialized."""
        with patch("merino.providers.widgets._travel_provider", None):
            with pytest.raises(ValueError, match="Travel provider has not been initialized."):
                get_travel_provider()

    @pytest.mark.asyncio
    async def test_shutdown_providers_shuts_down_travel_provider(self) -> None:
        """Shuts down the travel provider's backend and clears module state."""
        backend_mock = AsyncMock(name="mock_kayak_backend")
        provider = TravelProvider(backend=backend_mock, metrics_client=Mock(), name="test_travel")

        with (
            patch("merino.providers.widgets._wrexham_provider", None),
            patch("merino.providers.widgets._travel_provider", provider),
        ):
            await shutdown_providers()
            assert widgets._travel_provider is None

        backend_mock.shutdown.assert_awaited_once()


class TestFramedWidgetsProvider:
    """Test the FramedWidget provider."""

    @pytest.mark.asyncio
    async def test_init_providers(self) -> None:
        """Test for the `init_providers` method of the widgets provider"""
        with (
            patch("merino.providers.widgets._framed_widgets_provider_enabled", True),
            patch("merino.providers.widgets.get_metrics_client") as mock_get_metrics_client,
        ):
            mock_metrics_client_instance = Mock(name="mock_metrics_client")
            mock_get_metrics_client.return_value = mock_metrics_client_instance

            await init_providers()

            iframed_widget_provider = widgets._framed_widgets_provider

            assert isinstance(iframed_widget_provider, FramedWidgetProvider)
            assert iframed_widget_provider.name == "iframed Widgets Provider"
            assert iframed_widget_provider.metrics_client == mock_metrics_client_instance

            mock_get_metrics_client.assert_called()

    @pytest.mark.asyncio
    async def test_init_providers_when_gcs_client_fails(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Disable the cron, but still create every provider, when the GCS client fails."""
        with (
            patch("merino.providers.widgets._framed_widgets_provider_cron_enabled", True),
            patch(
                "merino.providers.widgets.initialize_storage_client",
                side_effect=Exception("no credentials"),
            ),
        ):
            await init_providers()

        provider = get_framed_widgets_provider()

        # The framed provider still exists, with no backend and no cron task.
        assert provider.backend is None
        assert provider.cron_task is None

        # The other providers were not affected by the GCS failure.
        assert isinstance(get_travel_provider(), TravelProvider)
        assert isinstance(get_wrexham_provider(), WrexhamProvider)

        # The failure was logged with the error in `extra`.
        records = [r for r in caplog.records if "Failed to create GCS client" in r.message]
        assert len(records) == 1
        assert records[0].levelname == "WARNING"
        assert records[0].__dict__["error_message"] == "no credentials"

        await shutdown_providers()

    @pytest.mark.asyncio
    async def test_get_framed_widgets_provider_initialized(self) -> None:
        """Verify get_framed_widgets_provider returns class instance after init_providers call."""
        await init_providers()

        assert isinstance(get_framed_widgets_provider(), FramedWidgetProvider)

    def test_get_framed_widgets_provider_not_initialized(self) -> None:
        """Verify that get_framed_widgets_provider raises ValueError when _framed_widget_provider is not initialized."""
        with patch("merino.providers.widgets._framed_widgets_provider", None):
            with pytest.raises(
                ValueError, match="iframed widgets provider has not been initialized."
            ):
                get_framed_widgets_provider()
