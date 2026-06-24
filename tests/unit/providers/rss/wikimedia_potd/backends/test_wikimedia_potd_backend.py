# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the Wikimedia Picture of the Day backend."""

import logging
import pytest
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock
from pydantic import HttpUrl
from httpx import AsyncClient, Request, Response
from pytest import LogCaptureFixture
from pytest_mock import MockerFixture

from merino.utils.gcs.gcs_uploader import GcsUploader
from merino.providers.rss.wikimedia_potd.backends.utils import RSS_FETCH_REQUEST_HEADERS
from merino.providers.rss.wikimedia_potd.backends.wikimedia_potd import (
    WikimediaPotdBackend,
)
from merino.utils.gcs.models import Image
from tests.data.rss.wikimedia_potd.potd_feed import TEST_RSS_FEED

FEED_URL = "https://example.com/feed"

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
def fixture_backend(statsd_mock, mocker: MockerFixture, gcs_uploader_mock) -> WikimediaPotdBackend:
    """Return a WikimediaPotdBackend instance for testing."""
    return WikimediaPotdBackend(
        metrics_client=statsd_mock,
        http_client=mocker.AsyncMock(spec=AsyncClient),
        feed_url=FEED_URL,
        gcs_uploader=gcs_uploader_mock,
    )


class TestWikimediaPotdBackend:
    """Tests for WikimediaPotd backend methods."""

    class TestDownloadAndUploadPotdImagesMethod:
        """Tests for download_and_upload_potd_images method."""

    @pytest.mark.asyncio
    async def test_download_and_upload_potd_images_returns_true_for_correct_xml_response(
        self, backend, mocker: MockerFixture
    ) -> None:
        """Test that download_and_upload_potd_images method returns true for correct xml response."""
        client_mock: AsyncMock = cast(AsyncMock, backend.http_client)

        # mocking http client to respond with the correct xml
        client_mock.get.return_value = Response(
            status_code=200,
            content=TEST_RSS_FEED,
            request=Request(method="GET", url=FEED_URL),
        )

        # mocking the download and upload methods to return happy path responses
        mocker.patch.object(backend, "download_potd_image").return_value = Image(
            content=b"255", content_type="Image/jpeg"
        )
        mocker.patch.object(backend, "upload_potd_image").return_value = HttpUrl(
            "https://www.test-image.com/image.jpeg"
        )

        result = await backend.download_and_upload_potd_images()
        assert result is True

    @pytest.mark.asyncio
    async def test_download_and_upload_potd_images_returns_false_when_no_rss_feed_is_fetched_with_200_ok(
        self, backend
    ) -> None:
        """Test that download_and_upload_potd_images method returns false when no rss feed is fetched."""
        client_mock: AsyncMock = cast(AsyncMock, backend.http_client)

        # mocking http client to respond with no xml
        client_mock.get.return_value = Response(
            status_code=200,
            content=None,
            request=Request(method="GET", url=FEED_URL),
        )

        result = await backend.download_and_upload_potd_images()
        assert result is False

    @pytest.mark.asyncio
    async def test_download_and_upload_potd_images_returns_false_when_response_is_not_200_ok(
        self, backend
    ) -> None:
        """Test that download_and_upload_potd_images method returns false response returns a 500 error."""
        client_mock: AsyncMock = cast(AsyncMock, backend.http_client)

        # mocking http client to respond with a 500 error
        client_mock.get.return_value = Response(
            status_code=500,
            content=None,
            request=Request(method="GET", url=FEED_URL),
        )

        result = await backend.download_and_upload_potd_images()
        assert result is False

    @pytest.mark.asyncio
    async def test_download_and_upload_potd_images_returns_false_when_parsing_fails(
        self, backend
    ) -> None:
        """Test that download_and_upload_potd_images method returns false when an parsing fails on invalid xml response."""
        client_mock: AsyncMock = cast(AsyncMock, backend.http_client)

        # mocking http client to respond with incorrect xml
        client_mock.get.return_value = Response(
            status_code=200,
            content=TEST_RSS_FEED_MISSING_FIELDS,
            request=Request(method="GET", url=FEED_URL),
        )

        result = await backend.download_and_upload_potd_images()
        assert result is False

    @pytest.mark.asyncio
    async def test_download_and_upload_potd_images_returns_false_when_downloading_image_fails(
        self, backend, mocker: MockerFixture
    ) -> None:
        """Test that download_and_upload_potd_images method returns false when downloading image fails."""
        client_mock: AsyncMock = cast(AsyncMock, backend.http_client)
        client_mock.get.return_value = Response(
            status_code=200,
            content=TEST_RSS_FEED,
            request=Request(method="GET", url=FEED_URL),
        )

        # mocking download_potd_image method to return None
        mocker.patch.object(backend, "download_potd_image").return_value = None

        result = await backend.download_and_upload_potd_images()
        assert result is False

    @pytest.mark.asyncio
    async def test_download_and_upload_potd_images_returns_false_when_uploading_image_fails(
        self, backend, mocker: MockerFixture
    ) -> None:
        """Test that download_and_upload_potd_images method returns false when uploading image fails."""
        client_mock: AsyncMock = cast(AsyncMock, backend.http_client)
        client_mock.get.return_value = Response(
            status_code=200,
            content=TEST_RSS_FEED,
            request=Request(method="GET", url=FEED_URL),
        )

        # mocking download method to return a valid value but not for the upload method
        mocker.patch.object(backend, "download_potd_image").return_value = Image(
            content=b"255", content_type="Image/jpeg"
        )
        mocker.patch.object(backend, "upload_potd_image").return_value = None

        result = await backend.download_and_upload_potd_images()
        assert result is False

    class TestFetchPictureOfTheDayFromFeedMethod:
        """Tests for fetch_picture_of_the_day method."""

        @pytest.mark.asyncio
        async def test_fetch_potd_returns_entry_on_success(
            self,
            backend: WikimediaPotdBackend,
        ) -> None:
            """Returns a FeedParserDict entry when the feed is fetched and parsed successfully."""
            client_mock: AsyncMock = cast(AsyncMock, backend.http_client)
            client_mock.get.return_value = Response(
                status_code=200,
                content=TEST_RSS_FEED.encode(),
                request=Request(method="GET", url=FEED_URL),
            )

            result = await backend.fetch_picture_of_the_day_from_feed()

            assert result is not None
            assert result["title"] == "Wikimedia Commons picture of the day for June 24"
            assert result["published"] == "Wed, 24 Jun 2026 00:00:00 GMT"
            client_mock.get.assert_called_once_with(FEED_URL, headers=RSS_FETCH_REQUEST_HEADERS)

        @pytest.mark.asyncio
        async def test_fetch_potd_returns_none_for_empty_content(
            self,
            backend: WikimediaPotdBackend,
        ) -> None:
            """Returns None when the HTTP response body is empty."""
            client_mock: AsyncMock = cast(AsyncMock, backend.http_client)
            client_mock.get.return_value = Response(
                status_code=200,
                content=b"",
                request=Request(method="GET", url=FEED_URL),
            )

            result = await backend.fetch_picture_of_the_day_from_feed()

            assert result is None

        @pytest.mark.asyncio
        async def test_fetch_potd_returns_none_and_logs_on_http_error(
            self,
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
            result = await backend.fetch_picture_of_the_day_from_feed()

            assert result is None
            records = filter_caplog(
                caplog.records,
                "merino.providers.rss.wikimedia_potd.backends.wikimedia_potd",
            )
            assert len(records) == 1
            assert "HTTP error occurred when fetching Wikimedia POTD feed" in records[0].message

        @pytest.mark.asyncio
        async def test_fetch_potd_returns_none_when_feed_has_no_valid_entries(
            self,
            backend: WikimediaPotdBackend,
        ) -> None:
            """Returns None when the feed entries are missing required fields."""
            client_mock: AsyncMock = cast(AsyncMock, backend.http_client)
            client_mock.get.return_value = Response(
                status_code=200,
                content=TEST_RSS_FEED_MISSING_FIELDS.encode(),
                request=Request(method="GET", url=FEED_URL),
            )

            result = await backend.fetch_picture_of_the_day_from_feed()

            assert result is None
