"""Unit tests for the curated_recommendations module init/shutdown."""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import merino.curated_recommendations as cr_module
from merino.cache.redis import RedisAdapter
from merino.curated_recommendations.corpus_backends.redis_cache import (
    RedisCachedScheduledSurface,
    RedisCachedSections,
)
from merino.exceptions import CacheAdapterError


class TestInitCorpusCache:
    """Tests for _init_corpus_cache."""

    def test_disabled_returns_backends_unchanged(self) -> None:
        """When cache is not 'redis', return the original backends with no adapter."""
        surface = MagicMock()
        sections = MagicMock()

        with patch.object(cr_module, "settings") as mock_settings:
            mock_settings.curated_recommendations.corpus_cache.cache = "none"
            s, sec, adapter = cr_module._init_corpus_cache(surface, sections)

        assert s is surface
        assert sec is sections
        assert adapter is None

    def test_redis_wraps_backends(self) -> None:
        """When cache is 'redis', wrap backends with Redis-cached versions."""
        surface = MagicMock()
        sections = MagicMock()

        with (
            patch.object(cr_module, "settings") as mock_settings,
            patch.object(
                cr_module, "create_redis_clients", return_value=(MagicMock(), MagicMock())
            ),
            patch.object(cr_module, "get_metrics_client", return_value=MagicMock()),
        ):
            cache = mock_settings.curated_recommendations.corpus_cache
            cache.cache = "redis"
            cache.soft_ttl_sec = 60
            cache.hard_ttl_sec = 86400
            cache.lock_ttl_sec = 30
            cache.key_prefix = "test"

            s, sec, adapter = cr_module._init_corpus_cache(surface, sections)

        assert isinstance(s, RedisCachedScheduledSurface)
        assert isinstance(sec, RedisCachedSections)
        assert isinstance(adapter, RedisAdapter)

    def test_redis_error_falls_back(self, caplog: pytest.LogCaptureFixture) -> None:
        """When Redis initialization fails, return original backends with no adapter."""
        surface = MagicMock()
        sections = MagicMock()

        with (
            patch.object(cr_module, "settings") as mock_settings,
            patch.object(cr_module, "create_redis_clients", side_effect=Exception("conn refused")),
            caplog.at_level(logging.ERROR, logger="merino.curated_recommendations"),
        ):
            mock_settings.curated_recommendations.corpus_cache.cache = "redis"

            s, sec, adapter = cr_module._init_corpus_cache(surface, sections)

        assert s is surface
        assert sec is sections
        assert adapter is None
        assert any("Failed to initialize" in r.message for r in caplog.records)


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
