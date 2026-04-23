# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the Wikimedia Picture of the Day backend."""

import logging
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient, Request, Response
from pydantic import HttpUrl
from pytest import LogCaptureFixture
from pytest_mock import MockerFixture

from merino.utils.gcs.gcs_uploader import GcsUploader
from merino.providers.rss.wikimedia_potd.backends.utils import RSS_FETCH_REQUEST_HEADERS
from merino.providers.rss.wikimedia_potd.backends.wikimedia_potd import (
    WikimediaPotdBackend,
)

FEED_URL = "https://example.com/feed"

TEST_RSS_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Wikimedia Commons Picture of the Day</title>
    <item>
      <title>Test POTD Title</title>
      <description>Test description content</description>
      <pubDate>Mon, 13 Apr 2026 00:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>"""

TEST_RSS_FEED_MISSING_FIELDS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>Only Title No Other Fields</title>
    </item>
  </channel>
</rss>"""


@pytest.fixture(name="gcs_uploader_mock")
def fixture_gcs_uploader_mock() -> GcsUploader:
    """Return a mock GcsUploader."""
    return MagicMock(spec=GcsUploader)


@pytest.fixture(name="backend")
def fixture_backend(
    statsd_mock,
    mocker: MockerFixture,
    gcs_uploader_mock: GcsUploader,
) -> WikimediaPotdBackend:
    """Return a WikimediaPotdBackend instance for testing."""
    return WikimediaPotdBackend(
        metrics_client=statsd_mock,
        http_client=mocker.AsyncMock(spec=AsyncClient),
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
    assert result.description == "Sample Picture of the day description."
    assert isinstance(result.thumbnail_image_url, HttpUrl)
    assert isinstance(result.high_res_image_url, HttpUrl)


@pytest.mark.asyncio
async def test_fetch_potd_returns_entry_on_success(
    backend: WikimediaPotdBackend,
) -> None:
    """Returns a FeedParserDict entry when the feed is fetched and parsed successfully."""
    client_mock: AsyncMock = cast(AsyncMock, backend.http_client)
    client_mock.get.return_value = Response(
        status_code=200,
        content=TEST_RSS_FEED.encode(),
        request=Request(method="GET", url=FEED_URL),
    )

    result = await backend.fetch_picture_of_the_day()

    assert result is not None
    assert result["title"] == "Test POTD Title"
    assert result["published"] == "Mon, 13 Apr 2026 00:00:00 GMT"
    client_mock.get.assert_called_once_with(FEED_URL, headers=RSS_FETCH_REQUEST_HEADERS)


@pytest.mark.asyncio
async def test_fetch_potd_returns_none_for_empty_content(
    backend: WikimediaPotdBackend,
) -> None:
    """Returns None when the HTTP response body is empty."""
    client_mock: AsyncMock = cast(AsyncMock, backend.http_client)
    client_mock.get.return_value = Response(
        status_code=200,
        content=b"",
        request=Request(method="GET", url=FEED_URL),
    )

    result = await backend.fetch_picture_of_the_day()

    assert result is None


@pytest.mark.asyncio
async def test_fetch_potd_returns_none_and_logs_on_http_error(
    backend: WikimediaPotdBackend,
    caplog: LogCaptureFixture,
    filter_caplog: Any,
) -> None:
    """Returns None and logs an error when the HTTP request fails with a non-2xx status."""
    client_mock: AsyncMock = cast(AsyncMock, backend.http_client)
    client_mock.get.return_value = Response(
        status_code=500,
        request=Request(method="GET", url=FEED_URL),
    )

    caplog.set_level(logging.ERROR)
    result = await backend.fetch_picture_of_the_day()

    assert result is None
    records = filter_caplog(
        caplog.records,
        "merino.providers.rss.wikimedia_potd.backends.wikimedia_potd",
    )
    assert len(records) == 1
    assert "HTTP error occurred when fetching Wikimedia POTD feed" in records[0].message


@pytest.mark.asyncio
async def test_fetch_potd_returns_none_when_feed_has_no_valid_entries(
    backend: WikimediaPotdBackend,
) -> None:
    """Returns None when the feed entries are missing required fields."""
    client_mock: AsyncMock = cast(AsyncMock, backend.http_client)
    client_mock.get.return_value = Response(
        status_code=200,
        content=TEST_RSS_FEED_MISSING_FIELDS.encode(),
        request=Request(method="GET", url=FEED_URL),
    )

    result = await backend.fetch_picture_of_the_day()

    assert result is None
