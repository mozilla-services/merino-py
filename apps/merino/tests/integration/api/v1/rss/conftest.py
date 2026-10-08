# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Test configurations for the rss API endpoint tests."""

from typing import Any

import pytest
from pytest_mock import MockerFixture
from pydantic import HttpUrl

from merino.main import app
from merino.providers.rss import get_wikimedia_potd_provider
from merino.providers.rss.wikimedia_potd.backends.protocol import (
    PictureOfTheDay,
    PictureOfTheDayBase,
    WikimediaPictureOfTheDayBackend,
)
from merino.providers.rss.wikimedia_potd.provider import WikimediaPictureOfTheDayProvider


@pytest.fixture(name="backend_mock")
def fixture_backend_mock(mocker: MockerFixture) -> Any:
    """Create a WikimediaPictureOfTheDayBackend mock object for test."""
    return mocker.AsyncMock(spec=WikimediaPictureOfTheDayBackend)


@pytest.fixture(name="potd_provider")
def fixture_potd_provider(backend_mock: Any, statsd_mock: Any) -> WikimediaPictureOfTheDayProvider:
    """Create a picture of the day provider with a mocked backend."""
    return WikimediaPictureOfTheDayProvider(
        backend=backend_mock,
        metrics_client=statsd_mock,
        name="wikimedia_potd",
        query_timeout_sec=1.0,
        enabled_by_default=True,
    )


@pytest.fixture(name="potd")
def fixture_potd() -> PictureOfTheDay:
    """Return a picture of the day carrying the previous day, both localized into German."""
    return PictureOfTheDay(
        title="Wikimedia Commons Picture of the Day for June 7",
        published_date="2026-06-07",
        thumbnail_image_url=HttpUrl("https://test-cdn/wikimedia_potd/2026-06-07/thumbnail.png"),
        high_res_image_url=HttpUrl("https://test-cdn/wikimedia_potd/2026-06-07/hi_res.webp"),
        description="Today's description.",
        localized_descriptions={"de": "Heutiger deutscher Text"},
        author="Test Artist",
        file_page=HttpUrl("https://commons.wikimedia.org/wiki/File:Today.jpg"),
        license_label="CC BY-SA 4.0",
        license_link=HttpUrl("https://creativecommons.org/licenses/by-sa/4.0"),
        previous=PictureOfTheDayBase(
            title="Wikimedia Commons Picture of the Day for June 6",
            published_date="2026-06-06",
            thumbnail_image_url=HttpUrl(
                "https://test-cdn/wikimedia_potd/2026-06-06/thumbnail.png"
            ),
            high_res_image_url=HttpUrl("https://test-cdn/wikimedia_potd/2026-06-06/hi_res.webp"),
            description="Yesterday's description.",
            localized_descriptions={"de": "Gestriger deutscher Text"},
            author="Previous Artist",
            file_page=HttpUrl("https://commons.wikimedia.org/wiki/File:Yesterday.jpg"),
            license_label="CC BY-SA 4.0",
            license_link=HttpUrl("https://creativecommons.org/licenses/by-sa/4.0"),
        ),
    )


@pytest.fixture(name="inject_potd_provider", autouse=True)
def fixture_inject_potd_provider(potd_provider: WikimediaPictureOfTheDayProvider):
    """Inject the picture of the day provider into the app for testing."""

    def get_test_potd_provider() -> WikimediaPictureOfTheDayProvider:
        return potd_provider

    app.dependency_overrides[get_wikimedia_potd_provider] = get_test_potd_provider
    yield
    del app.dependency_overrides[get_wikimedia_potd_provider]
