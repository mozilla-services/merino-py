# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the Wikimedia Picture of the Day provider."""

import pytest

from merino.providers.rss.wikimedia_potd.provider import Potd, WikimediaPotdProvider


@pytest.fixture(name="provider")
def fixture_provider(statsd_mock) -> WikimediaPotdProvider:
    """Return a WikimediaPotdProvider instance for testing."""
    return WikimediaPotdProvider(
        backend=None,
        metrics_client=statsd_mock,
        name="wikimedia_potd",
        query_timeout_sec=1.0,
        enabled_by_default=False,
    )


def test_provider_name(provider: WikimediaPotdProvider) -> None:
    """Test that the provider name is set correctly."""
    assert provider.name == "wikimedia_potd"


def test_provider_enabled_by_default(provider: WikimediaPotdProvider) -> None:
    """Test that enabled_by_default is set correctly."""
    assert provider.enabled_by_default is False


def test_provider_query_timeout_sec(provider: WikimediaPotdProvider) -> None:
    """Test that query_timeout_sec is set correctly."""
    assert provider.query_timeout_sec == 1.0


@pytest.mark.asyncio
async def test_initialize(provider: WikimediaPotdProvider) -> None:
    """Test that initialize completes without error."""
    await provider.initialize()


@pytest.mark.asyncio
async def test_shutdown(provider: WikimediaPotdProvider) -> None:
    """Test that shutdown completes without error."""
    await provider.shutdown()


@pytest.mark.asyncio
async def test_get_picture_of_the_day(provider: WikimediaPotdProvider) -> None:
    """Test that get_picture_of_the_day returns a Potd with empty fields."""
    potd = await provider.get_picture_of_the_day()

    assert isinstance(potd, Potd)
    assert potd.title == ""
    assert potd.image_url == ""
