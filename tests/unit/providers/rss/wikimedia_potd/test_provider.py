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


@pytest.mark.asyncio
async def test_initialize_leaves_cached_potd_unchanged_when_fetch_returns_none(
    provider: WikimediaPictureOfTheDayProvider, backend_mock
) -> None:
    """Test that initialize leaves cached potd unchanged when the backend fetch returns nothing."""
    backend_mock.fetch_potd_from_gcs_bucket.return_value = None

    await provider.initialize()
    # self.potd in provider was never set so it remains None
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


@freezegun.freeze_time("2026-06-07")
@pytest.mark.asyncio
async def test_get_picture_of_the_day_returns_fetched_potd_when_backend_fetch_is_not_stale(
    provider: WikimediaPictureOfTheDayProvider, backend_mock, test_potd
) -> None:
    """Test that get_picture_of_the_day returns a non-stale Potd when backend returns one."""
    backend_mock.fetch_potd_from_gcs_bucket.return_value = test_potd

    assert await provider.get_picture_of_the_day() is not None


@freezegun.freeze_time("2026-06-08")
@pytest.mark.asyncio
async def test_get_picture_of_the_day_caches_and_returns_fetched_potd(
    provider: WikimediaPictureOfTheDayProvider, backend_mock, test_potd
) -> None:
    """Test that a potd returned by the fetch is cached and served."""
    backend_mock.fetch_potd_from_gcs_bucket.return_value = test_potd

    potd = await provider.get_picture_of_the_day()

    assert potd is test_potd
    assert provider.potd is test_potd


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
async def test_get_picture_of_the_day_serves_stale_potd_when_refetch_misses(
    provider: WikimediaPictureOfTheDayProvider, backend_mock, test_potd
) -> None:
    """Test that a stale cached potd is served when today's potd cannot be fetched."""
    # cached test_potd is published 2026-06-07, a day old compared to the freeze time
    provider.potd = test_potd
    backend_mock.fetch_potd_from_gcs_bucket.return_value = None

    potd = await provider.get_picture_of_the_day()

    backend_mock.fetch_potd_from_gcs_bucket.assert_called_once()
    assert potd is test_potd


@freezegun.freeze_time("2026-06-07")
@pytest.mark.asyncio
async def test_get_picture_of_the_day_returns_localized_description_for_accepted_language(
    provider: WikimediaPictureOfTheDayProvider, test_potd
) -> None:
    """Swaps in the localized description matching the client's Accept-Language."""
    provider.potd = test_potd.model_copy(
        update={"localized_descriptions": {"de": "Deutscher Text"}}
    )

    potd = await provider.get_picture_of_the_day(["de-DE", "en-US"])

    assert potd is not None
    assert potd.description == "Deutscher Text"
    # the cached model is left untouched; only the returned copy is localized
    assert provider.potd.description == "test description"


@freezegun.freeze_time("2026-06-07")
@pytest.mark.asyncio
async def test_get_picture_of_the_day_matches_base_subtag(
    provider: WikimediaPictureOfTheDayProvider, test_potd
) -> None:
    """Falls back to the base language subtag when the full code has no description."""
    provider.potd = test_potd.model_copy(update={"localized_descriptions": {"pt": "Português"}})

    potd = await provider.get_picture_of_the_day(["pt-BR"])

    assert potd is not None
    assert potd.description == "Português"


@freezegun.freeze_time("2026-06-07")
@pytest.mark.asyncio
async def test_get_picture_of_the_day_prefers_exact_code_over_base_subtag(
    provider: WikimediaPictureOfTheDayProvider, test_potd
) -> None:
    """Prefers an exact language-code match over the base subtag match."""
    provider.potd = test_potd.model_copy(
        update={"localized_descriptions": {"pt": "Português", "pt-br": "Português brasileiro"}}
    )

    potd = await provider.get_picture_of_the_day(["pt-BR"])

    assert potd is not None
    assert potd.description == "Português brasileiro"


@freezegun.freeze_time("2026-06-07")
@pytest.mark.asyncio
async def test_get_picture_of_the_day_keeps_default_when_no_language_matches(
    provider: WikimediaPictureOfTheDayProvider, test_potd
) -> None:
    """Serves the default description (and the cached instance) when no language matches."""
    provider.potd = test_potd.model_copy(update={"localized_descriptions": {"de": "Deutscher Text"}})

    potd = await provider.get_picture_of_the_day(["fr-FR"])

    assert potd is provider.potd
    assert potd.description == "test description"


@freezegun.freeze_time("2026-06-07")
@pytest.mark.asyncio
async def test_get_picture_of_the_day_keeps_default_when_no_accepted_languages(
    provider: WikimediaPictureOfTheDayProvider, test_potd
) -> None:
    """Returns the cached instance unchanged when no Accept-Language is provided."""
    provider.potd = test_potd.model_copy(update={"localized_descriptions": {"de": "Deutscher Text"}})

    potd = await provider.get_picture_of_the_day()

    assert potd is provider.potd
    assert potd.description == "test description"


@freezegun.freeze_time("2026-06-08")
@pytest.mark.asyncio
async def test_get_picture_of_the_day_refetches_on_every_miss(
    provider: WikimediaPictureOfTheDayProvider, backend_mock
) -> None:
    """Test that each request re-fetches while nothing is cached and no potd is available."""
    backend_mock.fetch_potd_from_gcs_bucket.return_value = None

    assert await provider.get_picture_of_the_day() is None
    assert await provider.get_picture_of_the_day() is None

    # No throttling: the re-fetch is attempted on every request.
    assert backend_mock.fetch_potd_from_gcs_bucket.call_count == 2
