"""Unit tests for the massive ingestion class"""

import pytest
from unittest.mock import AsyncMock

from merino.jobs.massive.massive_ingestion import MassiveIngestion


@pytest.fixture
def patched_provider(mocker):
    """Return a mock Provider with a mock MassiveBackend."""
    mock_provider = mocker.MagicMock()
    mock_backend = mocker.MagicMock()
    mock_provider.backend = mock_backend
    return mock_provider, mock_backend


@pytest.mark.asyncio
async def test_ingest_triggers_upload_and_shutdown(mocker, patched_provider):
    """Test that ingest() calls the expected backend methods."""
    mock_provider, mock_backend = patched_provider

    mocker.patch(
        "merino.jobs.massive.massive_ingestion.MassiveIngestion.get_provider",
        return_value=mock_provider,
    )

    mock_backend.build_and_upload_manifest_file = AsyncMock()
    mock_backend.shutdown = AsyncMock()

    ingestion = MassiveIngestion()

    await ingestion.ingest()

    mock_backend.build_and_upload_manifest_file.assert_awaited_once()
    mock_backend.shutdown.assert_awaited_once()


def test_provider_instantiation(mocker):
    """Ensure get_provider builds a Provider with a backend."""
    mocker.patch("merino.providers.suggest.finance.backends.massive.backend.MassiveFilemanager")

    ingestion = MassiveIngestion()
    provider = ingestion.get_provider()

    assert provider is not None
    assert hasattr(provider, "backend")
