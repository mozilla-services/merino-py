"""Unit tests for the get_icon_url method of the manifest provider."""

import logging

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


MS_ICON = HttpUrl(
    "https://merino-images.services.mozilla.com/favicons/"
    "90cdaf487716184e4034000935c605d1633926d348116d198f355a98b8c6cd21_17174.oct"
)
BBC_ICON = HttpUrl("https://merino-images.services.mozilla.com/favicons/bbciconhash_12345.png")
# CNN_ICON = HttpUrl("https://merino-images.services.mozilla.com/favicons/cnniconhash_98765.png")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "test_url, expected_icon",
    [
        ("https://google.com/search", None),  # Google icon fixture is empty
        ("http://www.google.com", None),
        ("https://google.com", None),
        ("http://google.com/maps", None),
        ("https://www.microsoft.com/en-us/", MS_ICON),
        ("https://bbc.co.uk/news", BBC_ICON),
        ("https://www.bbc.co.uk/sport", BBC_ICON),
        # DISCO-3447: URLs with subdomains aren't handled correctly yet.
        # (
        #     "https://edition.cnn.com/2025/04/09/entertainment/aimee-lou-wood-teeth-talk-intl-scli/"
        #     "index.html?utm_source=firefox-newtab-en-us",
        #     CNN_ICON,
        # ),
    ],
)
async def test_get_icon_url_domain_variants(
    manifest_provider: Provider,
    manifest_data: ManifestData,
    cleanup,
    test_url,
    expected_icon,
):
    """Test icon URL retrieval with different domain format variants."""
    with patch(
        "merino.providers.manifest.backends.manifest.ManifestBackend.fetch",
        return_value=(GetManifestResultCode.SUCCESS, manifest_data),
    ):
        await manifest_provider.initialize()
        await cleanup(manifest_provider)

        assert manifest_provider.get_icon_url(test_url) == expected_icon


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
        assert manifest_provider.get_icon_url(url) is None  # Google has empty icon


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "icon_value,expected_log_msg",
    [
        ("", "Invalid icon URL for domain google: ''"),
        ("not-a-valid-url", "Invalid icon URL for domain google: 'not-a-valid-url'"),
    ],
)
async def test_get_icon_url_invalid_icon_logged(
    manifest_provider: Provider,
    manifest_data: ManifestData,
    cleanup,
    icon_value: str,
    expected_log_msg: str,
    caplog: pytest.LogCaptureFixture,
):
    """Test that invalid icon values log warnings and return None."""
    # Override the Google icon value
    for domain in manifest_data.domains:
        if domain.domain == "google":
            domain.icon = icon_value

    with patch(
        "merino.providers.manifest.backends.manifest.ManifestBackend.fetch",
        return_value=(GetManifestResultCode.SUCCESS, manifest_data),
    ):
        await manifest_provider.initialize()
        await cleanup(manifest_provider)

        assert manifest_provider.get_icon_url("https://www.google.com") is None

        assert any(
            record.message == expected_log_msg and record.levelno == logging.WARNING
            for record in caplog.records
        )
