# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the __init__ travel provider module."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

import merino.providers.travel as travel
from merino.providers.travel import get_travel_provider, init_providers, shutdown_providers
from merino.providers.travel.kayak.provider import Provider as TravelProvider


@pytest.mark.asyncio
async def test_init_providers() -> None:
    """Test for the `init_providers` method of the travel provider"""
    with (
        patch("merino.providers.travel._enabled", True),
        patch("merino.providers.travel._api_key", "mock_api_key"),
        patch("merino.providers.travel._url_base", "mock_url_base"),
        patch("merino.providers.travel._url_autocomplete_path", "mock_url_autocomplete_path"),
        patch("merino.providers.travel.create_http_client") as mock_create_http_client,
        patch("merino.providers.travel.get_metrics_client") as mock_get_metrics_client,
        patch("merino.providers.travel.KayakBackend") as mock_kayak_backend,
    ):
        mock_http_client_instance = Mock(name="mock_http_client")
        mock_create_http_client.return_value = mock_http_client_instance

        mock_metrics_client_instance = Mock(name="mock_metrics_client")
        mock_get_metrics_client.return_value = mock_metrics_client_instance

        mock_kayak_backend_instance = Mock(name="mock_kayak_backend")
        mock_kayak_backend.return_value = mock_kayak_backend_instance

        await init_providers()

        travel_provider = travel._travel_provider

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
        mock_get_metrics_client.assert_called_once()


@pytest.mark.asyncio
async def test_get_travel_provider_initialized() -> None:
    """Verify get_travel_provider returns class instance after init_providers call."""
    await init_providers()

    assert isinstance(get_travel_provider(), TravelProvider)


def test_get_travel_provider_not_initialized() -> None:
    """Verify that get_travel_provider raises ValueError when _travel_provider is not initialized."""
    with patch("merino.providers.travel._travel_provider", None):
        with pytest.raises(ValueError, match="Travel provider has not been initialized."):
            get_travel_provider()


@pytest.mark.asyncio
async def test_shutdown_providers() -> None:
    """Verify that shutdown_providers shuts down the travel provider's backend."""
    backend_mock = AsyncMock(name="mock_kayak_backend")
    provider = TravelProvider(backend=backend_mock, metrics_client=Mock(), name="test_travel")

    with patch("merino.providers.travel._travel_provider", provider):
        await shutdown_providers()

    backend_mock.shutdown.assert_awaited_once()
