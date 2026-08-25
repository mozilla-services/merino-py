"""Unit tests for the polygon ingestion class"""

import pytest
from unittest.mock import AsyncMock

from merino.jobs.polygon.polygon_ingestion import PolygonIngestion


@pytest.fixture
def patched_provider(mocker):
    """Return a mock Provider with a mock PolygonBackend."""
    mock_provider = mocker.MagicMock()
    mock_backend = mocker.MagicMock()
    mock_provider.backend = mock_backend
    return mock_provider, mock_backend


@pytest.mark.asyncio
async def test_ingest_triggers_upload_and_shutdown(mocker, patched_provider):
    """Test that ingest() calls the expected backend methods."""
    mock_provider, mock_backend = patched_provider

    mocker.patch(
        "merino.jobs.polygon.polygon_ingestion.PolygonIngestion.get_provider",
        return_value=mock_provider,
    )

    mock_backend.build_and_upload_manifest_file = AsyncMock()
    mock_backend.shutdown = AsyncMock()

    ingestion = PolygonIngestion()

    await ingestion.ingest()

    mock_backend.build_and_upload_manifest_file.assert_awaited_once()
    mock_backend.shutdown.assert_awaited_once()


def test_provider_instantiation(mocker):
    """Ensure get_provider builds a Provider with a backend."""
    mocker.patch("merino.providers.suggest.finance.backends.polygon.backend.PolygonFilemanager")

    ingestion = PolygonIngestion()
    provider = ingestion.get_provider()

    assert provider is not None
    assert hasattr(provider, "backend")
