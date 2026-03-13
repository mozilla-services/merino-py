"""Unit tests for the curated_recommendations module init/shutdown."""

import logging
from unittest.mock import AsyncMock

import pytest

import merino.curated_recommendations as cr_module
from merino.exceptions import CacheAdapterError


class TestShutdown:
    """Tests for curated_recommendations.shutdown() error handling."""

    @pytest.mark.asyncio
    async def test_shutdown_does_not_propagate_close_error(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Shutdown should log a warning and not propagate exceptions from provider.shutdown()."""
        mock_provider = AsyncMock()
        mock_provider.shutdown.side_effect = CacheAdapterError("connection reset")
        monkeypatch.setattr(cr_module, "_provider", mock_provider, raising=False)

        with caplog.at_level(logging.WARNING, logger="merino.curated_recommendations"):
            await cr_module.shutdown()

        assert any(
            "Error shutting down curated recommendations" in record.message
            for record in caplog.records
        )
