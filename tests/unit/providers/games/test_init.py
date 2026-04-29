# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the __init__ manifest provider module."""

from unittest.mock import Mock, patch
import pytest

from merino.providers.games import (
    get_particle_provider,
    init_providers,
)

from merino.providers.games.particle.provider import Provider as ParticleProvider


@pytest.mark.asyncio
async def test_init_providers() -> None:
    """Test for the `init_providers` method of the games provider"""
    with (
        patch("merino.providers.games._connect_timeout", "mock_connect_timeout"),
        patch("merino.providers.games._gcs_project", "mock_gcs_project"),
        patch("merino.providers.games._gcs_bucket", "mock_gcs_bucket"),
        patch("merino.providers.games._gcs_cdn_hostname", "mock_cdn_hostname"),
        patch("merino.providers.games._url_root", "mock_url_root"),
        patch("merino.providers.games._url_path_manifest", "mock_url_path_manifest"),
        patch("merino.providers.games.GcsUploader") as mock_gcs_uploader,
        patch("merino.providers.games.create_http_client") as mock_create_http_client,
        patch("merino.providers.games.get_metrics_client") as mock_get_metrics_client,
        patch("merino.providers.games.ParticleBackend") as mock_particle_backend,
    ):
        mock_gcs_uploader_instance = Mock(name="mock_gcs_uploader")
        mock_gcs_uploader.return_value = mock_gcs_uploader_instance

        mock_http_client_instance = Mock(name="mock_http_client")
        mock_create_http_client.return_value = mock_http_client_instance

        mock_metrics_client_instance = Mock(name="mock_metrics_client")
        mock_get_metrics_client.return_value = mock_metrics_client_instance

        mock_particle_backend_instance = Mock(name="mock_particle_backend")
        mock_particle_backend.return_value = mock_particle_backend_instance

        await init_providers()

        from merino.providers.games import _particle_provider

        assert _particle_provider is not None
        assert isinstance(_particle_provider, ParticleProvider)
        assert _particle_provider.name == "Particle Provider"
        assert _particle_provider.backend == mock_particle_backend_instance
        assert _particle_provider.metrics_client == mock_metrics_client_instance

        mock_gcs_uploader.assert_called_once_with(
            "mock_gcs_project", "mock_gcs_bucket", "mock_cdn_hostname"
        )
        mock_create_http_client.assert_called_once_with(connect_timeout="mock_connect_timeout")
        mock_get_metrics_client.assert_called_once()

        mock_particle_backend.assert_called_once_with(
            gcs_uploader=mock_gcs_uploader_instance,
            http_client=mock_http_client_instance,
            metrics_client=mock_metrics_client_instance,
            particle_url_root="mock_url_root",
            particle_url_path_manifest="mock_url_path_manifest",
        )


@pytest.mark.asyncio
async def test_get_particle_provider_initialized() -> None:
    """Verify get_particle_provider returns class instance after init_providers call."""
    await init_providers()

    assert isinstance(get_particle_provider(), ParticleProvider)


def test_get_particle_provider_not_initialized() -> None:
    """Verify that get_particle_provider raises ValueError when _particle_provider is not initialized."""
    with patch("merino.providers.games._particle_provider", None):
        with pytest.raises(ValueError, match="Particle provider has not been initialized."):
            get_particle_provider()
