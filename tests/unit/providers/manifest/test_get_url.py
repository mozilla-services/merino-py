"""Unit tests for the get_icon_url method of the manifest provider."""

import pytest
from pydantic import HttpUrl

from merino.providers.manifest.backends.protocol import GetManifestResultCode, ManifestData
from merino.providers.manifest.provider import Provider
from unittest.mock import patch


@pytest.mark.asyncio
async def test_domain_lookup_table_initialization(
    manifest_provider: Provider, manifest_data: ManifestData, cleanup
):
    """Test that domain_lookup_table is correctly initialized during provider setup."""
    with patch(
        "merino.providers.manifest.backends.manifest.ManifestBackend.fetch",
        return_value=(GetManifestResultCode.SUCCESS, manifest_data),
    ):
        await manifest_provider.initialize()
        await cleanup(manifest_provider)

        assert len(manifest_provider.domain_lookup_table) == len(manifest_data.domains)
        for domain in manifest_data.domains:
            assert domain.domain in manifest_provider.domain_lookup_table


@pytest.mark.asyncio
async def test_get_icon_url_success(
    manifest_provider: Provider, manifest_data: ManifestData, cleanup
):
    """Test successful icon URL retrieval for known domains."""
    with patch(
        "merino.providers.manifest.backends.manifest.ManifestBackend.fetch",
        return_value=(GetManifestResultCode.SUCCESS, manifest_data),
    ):
        await manifest_provider.initialize()
        await cleanup(manifest_provider)

        # Test with Google domain which exists in fixture
        google_icon = manifest_provider.get_icon_url("https://www.google.com/search")
        assert google_icon == ""  # Google has empty icon in fixture


@pytest.mark.asyncio
async def test_get_icon_url_domain_variants(
    manifest_provider: Provider, manifest_data: ManifestData, cleanup
):
    """Test icon URL retrieval with different domain format variants."""
    with patch(
        "merino.providers.manifest.backends.manifest.ManifestBackend.fetch",
        return_value=(GetManifestResultCode.SUCCESS, manifest_data),
    ):
        await manifest_provider.initialize()
        await cleanup(manifest_provider)

        test_cases = [
            "https://google.com/search",
            "http://www.google.com",
            "https://google.com",
            "http://google.com/maps",
        ]

        for url in test_cases:
            result = manifest_provider.get_icon_url(url)
            assert result == ""  # Google has empty icon in fixture


@pytest.mark.asyncio
async def test_get_icon_url_not_found(
    manifest_provider: Provider, manifest_data: ManifestData, cleanup
):
    """Test icon URL retrieval for non-existent domain."""
    with patch(
        "merino.providers.manifest.backends.manifest.ManifestBackend.fetch",
        return_value=(GetManifestResultCode.SUCCESS, manifest_data),
    ):
        await manifest_provider.initialize()
        await cleanup(manifest_provider)

        assert manifest_provider.get_icon_url("https://nonexistent.com") is None


@pytest.mark.asyncio
async def test_get_icon_url_invalid_url(
    manifest_provider: Provider, manifest_data: ManifestData, cleanup
):
    """Test icon URL retrieval with invalid URLs."""
    with patch(
        "merino.providers.manifest.backends.manifest.ManifestBackend.fetch",
        return_value=(GetManifestResultCode.SUCCESS, manifest_data),
    ):
        await manifest_provider.initialize()
        await cleanup(manifest_provider)

        invalid_urls = [
            "not-a-url",
            "http://",
            "",
            "google",  # Just a domain name without protocol
        ]

        for invalid_url in invalid_urls:
            assert manifest_provider.get_icon_url(invalid_url) is None


@pytest.mark.asyncio
async def test_get_icon_url_with_pydantic_url(
    manifest_provider: Provider, manifest_data: ManifestData, cleanup
):
    """Test icon URL retrieval with Pydantic HttpUrl type."""
    with patch(
        "merino.providers.manifest.backends.manifest.ManifestBackend.fetch",
        return_value=(GetManifestResultCode.SUCCESS, manifest_data),
    ):
        await manifest_provider.initialize()
        await cleanup(manifest_provider)

        url = HttpUrl("https://google.com/search")
        assert manifest_provider.get_icon_url(url) == ""  # Google has empty icon


@pytest.mark.asyncio
async def test_get_icon_url_empty_manifest(manifest_provider: Provider, cleanup):
    """Test icon URL retrieval with empty manifest data."""
    empty_manifest = ManifestData(domains=[])
    with patch(
        "merino.providers.manifest.backends.manifest.ManifestBackend.fetch",
        return_value=(GetManifestResultCode.SUCCESS, empty_manifest),
    ):
        await manifest_provider.initialize()
        await cleanup(manifest_provider)

        assert manifest_provider.get_icon_url("https://google.com") is None
