# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the Wikimedia Picture of the Day provider."""

import pytest
import freezegun
from pydantic.networks import HttpUrl
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
        thumbnail_image_url=HttpUrl("https://test-thumbnail.jpg"),
        high_res_image_url=HttpUrl("https://test-high-res.jpg"),
        description="test description",
        published_date="2026-06-07",
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


@freezegun.freeze_time("2026-06-07")
@pytest.mark.asyncio
async def test_initialize_caches_fresh_potd(
    provider: WikimediaPictureOfTheDayProvider, backend_mock, test_potd
) -> None:
    """Test that initialize caches the potd when the backend returns a fresh one."""
    backend_mock.fetch_potd_from_gcs_bucket.return_value = test_potd

    await provider.initialize()

    assert provider.potd is test_potd


@freezegun.freeze_time("2026-06-08")
@pytest.mark.asyncio
async def test_initialize_leaves_potd_none_when_fetch_is_stale_or_missing(
    provider: WikimediaPictureOfTheDayProvider, backend_mock, test_potd
) -> None:
    """Test that initialize leaves potd unset when the backend has no fresh potd."""
    # test_potd is published 2026-06-07, stale relative to the freeze time
    backend_mock.fetch_potd_from_gcs_bucket.return_value = test_potd

    await provider.initialize()

    assert provider.potd is None


@pytest.mark.asyncio
async def test_initialize_is_noop_when_potd_already_cached(
    provider: WikimediaPictureOfTheDayProvider, backend_mock, test_potd
) -> None:
    """Test that initialize does not re-fetch when a potd is already cached."""
    provider.potd = test_potd

    await provider.initialize()

    assert provider.potd is test_potd
    backend_mock.fetch_potd_from_gcs_bucket.assert_not_called()


@pytest.mark.asyncio
async def test_shutdown(provider: WikimediaPictureOfTheDayProvider) -> None:
    """Test that shutdown completes without error."""
    await provider.shutdown()


@pytest.mark.asyncio
async def test_upload_picture_of_the_day_delegates_to_backend(
    provider: WikimediaPictureOfTheDayProvider, backend_mock
) -> None:
    """Test that upload_picture_of_the_day delegates to the backend and returns its result."""
    backend_mock.upload_picture_of_the_day.return_value = True

    result = await provider.upload_picture_of_the_day()

    assert result is True
    backend_mock.upload_picture_of_the_day.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_picture_of_the_day_returns_none_when_backend_fetch_returns_none(
    provider: WikimediaPictureOfTheDayProvider, backend_mock
) -> None:
    """Test that get_picture_of_the_day returns an empty Potd when backend returns None."""
    backend_mock.fetch_potd_from_gcs_bucket.return_value = None
    assert await provider.get_picture_of_the_day() is None


@freezegun.freeze_time("2026-06-07")
@pytest.mark.asyncio
async def test_get_picture_of_the_day_returns_correct_potd_when_backend_fetch_returns_correct_potd(
    provider: WikimediaPictureOfTheDayProvider, backend_mock, test_potd
) -> None:
    """Test that get_picture_of_the_day returns a non-stale Potd when backend returns one."""
    backend_mock.fetch_potd_from_gcs_bucket.return_value = test_potd

    assert await provider.get_picture_of_the_day() is not None


@freezegun.freeze_time("2026-06-08")
@pytest.mark.asyncio
async def test_get_picture_of_the_day_returns_None_when_backend_fetch_returns_stale_potd(
    provider: WikimediaPictureOfTheDayProvider, backend_mock, test_potd
) -> None:
    """Test that get_picture_of_the_day returns None when backend returns a stale potd."""
    # test_potd has the published date as 2026-06-07, a day old compared to test freeze time
    backend_mock.fetch_potd_from_gcs_bucket.return_value = test_potd
    assert await provider.get_picture_of_the_day() is None


@freezegun.freeze_time("2026-06-07")
@pytest.mark.asyncio
async def test_get_picture_of_the_day_returns_cached_potd_when_not_stale(
    provider: WikimediaPictureOfTheDayProvider, backend_mock, test_potd
) -> None:
    """Test that a non-stale cached potd is returned directly without re-fetching."""
    provider.potd = test_potd

    potd = await provider.get_picture_of_the_day()

    assert potd is not None
    assert potd.title == "Wikimedia Commons picture of the day"
    assert potd.thumbnail_image_url == HttpUrl("https://test-thumbnail.jpg")
    assert potd.high_res_image_url == HttpUrl("https://test-high-res.jpg")
    assert potd.published_date == "2026-06-07"
    backend_mock.fetch_potd_from_gcs_bucket.assert_not_called()


@freezegun.freeze_time("2026-06-08")
@pytest.mark.asyncio
async def test_get_picture_of_the_day_refetches_when_cached_potd_is_stale(
    provider: WikimediaPictureOfTheDayProvider, backend_mock, test_potd
) -> None:
    """Test that a stale cached potd triggers a re-fetch and the fresh potd is returned."""
    # cached test_potd is published 2026-06-07, a day old compared to the freeze time
    provider.potd = test_potd
    fresh_potd = test_potd.model_copy(update={"published_date": "2026-06-08"})
    backend_mock.fetch_potd_from_gcs_bucket.return_value = fresh_potd

    potd = await provider.get_picture_of_the_day()

    backend_mock.fetch_potd_from_gcs_bucket.assert_called_once()
    assert potd is fresh_potd
    assert provider.potd is fresh_potd


@freezegun.freeze_time("2026-06-08")
@pytest.mark.asyncio
async def test_get_picture_of_the_day_returns_none_when_cached_stale_and_refetch_misses(
    provider: WikimediaPictureOfTheDayProvider, backend_mock, test_potd
) -> None:
    """Test that a stale cache with no fresh potd available returns None."""
    provider.potd = test_potd
    backend_mock.fetch_potd_from_gcs_bucket.return_value = None

    potd = await provider.get_picture_of_the_day()

    backend_mock.fetch_potd_from_gcs_bucket.assert_called_once()
    assert potd is None


@freezegun.freeze_time("2026-06-08")
@pytest.mark.asyncio
async def test_get_picture_of_the_day_reports_missing_potd_to_sentry_once(
    provider: WikimediaPictureOfTheDayProvider, backend_mock, mocker: MockerFixture
) -> None:
    """Test that repeated misses emit a single Sentry warning per stale window."""
    backend_mock.fetch_potd_from_gcs_bucket.return_value = None
    capture = mocker.patch(
        "merino.providers.rss.wikimedia_potd.provider.sentry_sdk.capture_message"
    )

    assert await provider.get_picture_of_the_day() is None
    assert await provider.get_picture_of_the_day() is None

    # Re-fetch happens on every request, but the warning is emitted only once.
    assert backend_mock.fetch_potd_from_gcs_bucket.call_count == 2
    capture.assert_called_once()
    message = capture.call_args.args[0]
    assert "Fetched published_date: none" in message
    assert "today: 2026-06-08" in message


@freezegun.freeze_time("2026-06-08")
@pytest.mark.asyncio
async def test_get_picture_of_the_day_sentry_message_includes_stale_published_date(
    provider: WikimediaPictureOfTheDayProvider, backend_mock, test_potd, mocker: MockerFixture
) -> None:
    """Test that the Sentry warning reports the fetched (stale) published date and today."""
    # test_potd is published 2026-06-07, stale relative to the freeze time
    backend_mock.fetch_potd_from_gcs_bucket.return_value = test_potd
    capture = mocker.patch(
        "merino.providers.rss.wikimedia_potd.provider.sentry_sdk.capture_message"
    )

    assert await provider.get_picture_of_the_day() is None

    message = capture.call_args.args[0]
    assert "Fetched published_date: 2026-06-07" in message
    assert "today: 2026-06-08" in message


@pytest.mark.asyncio
async def test_get_picture_of_the_day_reports_again_after_recovery(
    provider: WikimediaPictureOfTheDayProvider, backend_mock, test_potd, mocker: MockerFixture
) -> None:
    """Test that a fresh fetch resets the stale window so a later miss reports again."""
    capture = mocker.patch(
        "merino.providers.rss.wikimedia_potd.provider.sentry_sdk.capture_message"
    )

    # Day 1: miss -> one warning.
    with freezegun.freeze_time("2026-06-08"):
        backend_mock.fetch_potd_from_gcs_bucket.return_value = None
        assert await provider.get_picture_of_the_day() is None

    # Day 2: fresh potd available -> cached, stale window reset.
    with freezegun.freeze_time("2026-06-09"):
        fresh_potd = test_potd.model_copy(update={"published_date": "2026-06-09"})
        backend_mock.fetch_potd_from_gcs_bucket.return_value = fresh_potd
        assert await provider.get_picture_of_the_day() is fresh_potd

    # Day 3: miss again -> a second warning is emitted.
    with freezegun.freeze_time("2026-06-10"):
        backend_mock.fetch_potd_from_gcs_bucket.return_value = None
        assert await provider.get_picture_of_the_day() is None

    assert capture.call_count == 2
