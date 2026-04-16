# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the Wikimedia Picture of the Day provider."""

from pydantic.networks import HttpUrl
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


@pytest.fixture(name="test_potd")
def fixture_test_potd() -> PictureOfTheDay:
    """Return a test picture of the day instance."""
    return PictureOfTheDay(
        title="Wikimedia Commons picture of the day",
        thumbnail_image_url="https://test-thumbnail.jpg",
        high_res_image_url="https://test-high-res.jpg",
        description="test description",
        published_date="Mon, 13 Apr 2026 00:00:00 GMT",
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
async def test_get_picture_of_the_day_returns_none_when_backend_returns_none(
    provider: WikimediaPictureOfTheDayProvider, backend_mock
) -> None:
    """Test that get_picture_of_the_day returns an empty Potd when backend returns None."""
    backend_mock.get_picture_of_the_day.return_value = None

    potd = await provider.get_picture_of_the_day()

    assert potd is None


@pytest.mark.asyncio
async def test_get_picture_of_the_day_returns_correct_potd(
    provider: WikimediaPictureOfTheDayProvider, backend_mock, test_potd
) -> None:
    """Test that get_picture_of_the_day returns a correct potd instance."""
    backend_mock.get_picture_of_the_day.return_value = test_potd

    potd = await provider.get_picture_of_the_day()

    assert potd is not None
    assert potd.title == "Wikimedia Commons picture of the day"
    assert potd.thumbnail_image_url == HttpUrl("https://test-thumbnail.jpg")
    assert potd.high_res_image_url == HttpUrl("https://test-high-res.jpg")
    assert potd.published_date == "Mon, 13 Apr 2026 00:00:00 GMT"
