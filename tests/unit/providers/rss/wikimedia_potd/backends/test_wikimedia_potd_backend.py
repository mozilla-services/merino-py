# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the Wikimedia Picture of the Day backend."""

import pytest
from unittest.mock import MagicMock
from httpx import AsyncClient
from pydantic import HttpUrl

from merino.utils.gcs.gcs_uploader import GcsUploader
from merino.providers.rss.wikimedia_potd.backends.wikimedia_potd import (
    WikimediaPotdBackend,
)

FEED_URL = "https://example.com/feed"


@pytest.fixture(name="http_client_mock")
def fixture_http_client_mock() -> AsyncClient:
    """Return a mock AsyncClient."""
    return MagicMock(spec=AsyncClient)


@pytest.fixture(name="gcs_uploader_mock")
def fixture_gcs_uploader_mock() -> GcsUploader:
    """Return a mock GcsUploader."""
    return MagicMock(spec=GcsUploader)


@pytest.fixture(name="backend")
def fixture_backend(
    statsd_mock,
    http_client_mock: AsyncClient,
    gcs_uploader_mock: GcsUploader,
) -> WikimediaPotdBackend:
    """Return a WikimediaPotdBackend instance for testing."""
    return WikimediaPotdBackend(
        metrics_client=statsd_mock,
        http_client=http_client_mock,
        gcs_uploader=gcs_uploader_mock,
        feed_url=FEED_URL,
    )


@pytest.mark.asyncio
async def test_get_pitcture_of_the_day_returns_correct_potd(backend: WikimediaPotdBackend) -> None:
    """Test that get_picture_of_the_day method returns the correct potd instance."""
    result = await backend.get_picture_of_the_day()

    assert result is not None
    assert result.title == "Wikimedia Commons picture of the day"
    assert result.published_date == "Mon, 13 Apr 2026 00:00:00 GMT"
    assert isinstance(result.thumbnail_image_url, HttpUrl)
    assert isinstance(result.high_res_image_url, HttpUrl)
