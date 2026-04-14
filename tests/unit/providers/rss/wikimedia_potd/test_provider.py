# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the Wikimedia Picture of the Day provider."""

import pytest
from pytest_mock import MockerFixture

from merino.providers.rss.wikimedia_potd.backends.protocol import (
    PictureOfTheDay,
    WikimediaPictureOfTheDayBackend,
)
from merino.providers.rss.wikimedia_potd.provider import WikimediaPictureOfTheDayProvider


@pytest.fixture(name="backend_mock")
def fixture_backend_mock(mocker: MockerFixture):
    """Return a mock WikimediaPotdBackend."""
    return mocker.AsyncMock(spec=WikimediaPictureOfTheDayBackend)


@pytest.fixture(name="provider")
def fixture_provider(
    statsd_mock, backend_mock: WikimediaPictureOfTheDayBackend
) -> WikimediaPictureOfTheDayProvider:
    """Return a WikimediaPotdProvider instance for testing."""
    return WikimediaPictureOfTheDayProvider(
        backend=backend_mock,
        metrics_client=statsd_mock,
        name="wikimedia_potd",
        query_timeout_sec=1.0,
        enabled_by_default=False,
    )


def test_provider_name(provider: WikimediaPictureOfTheDayProvider) -> None:
    """Test that the provider name is set correctly."""
    assert provider.name == "wikimedia_potd"


def test_provider_enabled_by_default(provider: WikimediaPictureOfTheDayProvider) -> None:
    """Test that enabled_by_default is set correctly."""
    assert provider.enabled_by_default is False


def test_provider_query_timeout_sec(provider: WikimediaPictureOfTheDayProvider) -> None:
    """Test that query_timeout_sec is set correctly."""
    assert provider.query_timeout_sec == 1.0


@pytest.mark.asyncio
async def test_initialize(provider: WikimediaPictureOfTheDayProvider) -> None:
    """Test that initialize completes without error."""
    await provider.initialize()


@pytest.mark.asyncio
async def test_shutdown(provider: WikimediaPictureOfTheDayProvider) -> None:
    """Test that shutdown completes without error."""
    await provider.shutdown()


@pytest.mark.asyncio
async def test_get_picture_of_the_day_returns_default_when_backend_returns_none(
    provider: WikimediaPictureOfTheDayProvider, backend_mock
) -> None:
    """Test that get_picture_of_the_day returns an empty Potd when backend returns None."""
    backend_mock.get_picture_of_the_day.return_value = None

    potd = await provider.get_picture_of_the_day()

    assert isinstance(potd, PictureOfTheDay)
    assert potd.title == ""
    assert potd.thumbnail_image_url == ""
    assert potd.high_res_image_url == ""
    assert potd.published_date == ""
