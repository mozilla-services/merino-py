# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for utils.py module."""

import logging

import pytest
from pytest import LogCaptureFixture
from pytest_mock import MockerFixture

from merino.jobs.navigational_suggestions.utils import (
    AsyncFaviconDownloader,
    REQUEST_HEADERS,
)


@pytest.mark.asyncio
async def test_favicon_downloader(mock_favicon_downloader):
    """Test AsyncFaviconDownloader using the fixture"""
    # Create a pre-configured favicon downloader with mocked HTTP responses
    downloader = mock_favicon_downloader(content_type="image/x-icon", content=b"1")

    # Execute the test
    favicon = await downloader.download_favicon("http://icon")

    # Assertions
    assert favicon is not None
    assert favicon.content == b"1"
    assert favicon.content_type == "image/x-icon"


@pytest.mark.asyncio
async def test_requests_get_success(mocker):
    """Test that requests_get returns a response for successful requests"""
    # Create a mock response
    mock_response = mocker.AsyncMock()
    mock_response.status = 200
    mock_response.status_code = 200

    # Create the session mock
    mock_session = mocker.AsyncMock()
    mock_session.get.return_value = mock_response

    # Create the downloader and set the session
    downloader = AsyncFaviconDownloader()
    downloader.session = mock_session

    # Test the method
    response = await downloader.requests_get("http://example.com")

    # Verify the result
    assert response is mock_response
    mock_session.get.assert_called_once_with(
        "http://example.com", headers=REQUEST_HEADERS, follow_redirects=True
    )


@pytest.mark.asyncio
async def test_requests_get_non_200_status(mocker):
    """Test that requests_get returns None for non-200 status codes"""
    # Create a mock response with a non-200 status
    mock_response = mocker.AsyncMock()
    mock_response.status = 404
    mock_response.status_code = 404

    # Create the session mock
    mock_session = mocker.AsyncMock()
    mock_session.get.return_value = mock_response

    # Create the downloader and set the session
    downloader = AsyncFaviconDownloader()
    downloader.session = mock_session

    # Test the method
    response = await downloader.requests_get("http://example.com")

    # Verify the result
    assert response is None


@pytest.mark.asyncio
async def test_requests_get_exception(mocker, caplog):
    """Test that requests_get handles exceptions properly"""
    # Create the session mock that raises an exception
    mock_session = mocker.AsyncMock()
    mock_session.get.side_effect = Exception("Test error")

    # Create the downloader and set the session
    downloader = AsyncFaviconDownloader()
    downloader.session = mock_session

    # Set log level to capture info logs
    caplog.set_level("INFO")

    # Test the method
    response = await downloader.requests_get("http://example.com")

    # Verify the result
    assert response is None
    assert "Exception Test error while getting response from http://example.com" in caplog.text


@pytest.mark.asyncio
async def test_download_multiple_favicons(mocker):
    """Test that download_multiple_favicons calls download_favicon for each URL"""
    # Create a mock favicon image
    from merino.utils.gcs.models import Image

    test_favicon = Image(content=b"test", content_type="image/png")

    # Create a download_favicon mock that returns our test favicon
    async def mock_download_favicon(url):
        return test_favicon

    # Create the downloader
    downloader = AsyncFaviconDownloader()

    # Mock the download_favicon method
    mocker.patch.object(downloader, "download_favicon", side_effect=mock_download_favicon)

    # Test the method with multiple URLs
    urls = ["http://example1.com", "http://example2.com", "http://example3.com"]
    results = await downloader.download_multiple_favicons(urls)

    # Verify the results
    assert len(results) == len(urls)
    for favicon in results:
        assert favicon is test_favicon

    # Verify download_favicon was called for each URL
    assert downloader.download_favicon.call_count == len(urls)


@pytest.mark.asyncio
async def test_download_multiple_favicons_with_exceptions(mocker):
    """Test that download_multiple_favicons handles errors properly"""
    # Create a mock favicon image
    from merino.utils.gcs.models import Image

    test_favicon = Image(content=b"test", content_type="image/png")

    # Create a mock that alternates between returning favicon and raising exception
    async def mock_download_favicon(url):
        if url == "http://example2.com":
            raise Exception("Test exception")
        return test_favicon

    # Create the downloader
    downloader = AsyncFaviconDownloader()

    # Mock the download_favicon method
    mocker.patch.object(downloader, "download_favicon", side_effect=mock_download_favicon)

    # Test the method with multiple URLs
    urls = ["http://example1.com", "http://example2.com", "http://example3.com"]
    results = await downloader.download_multiple_favicons(urls)

    # Verify the results - we should have None for the URL that raised an exception
    assert len(results) == len(urls)
    assert results[0] is test_favicon
    assert results[1] is None  # This one raised an exception
    assert results[2] is test_favicon

    # Verify download_favicon was called for each URL
    assert downloader.download_favicon.call_count == len(urls)


@pytest.mark.asyncio
async def test_favicon_downloader_handles_exception(
    mocker: MockerFixture, caplog: LogCaptureFixture
):
    """Test AsyncFaviconDownloader exception handling"""
    caplog.set_level(logging.INFO)

    # Create the downloader
    downloader = AsyncFaviconDownloader()

    # Mock the session's get method to raise an exception
    mocker.patch.object(downloader.session, "get", side_effect=Exception("Bad Request"))

    favicon = await downloader.download_favicon("http://icon")

    assert favicon is None
    assert len(caplog.messages) == 1
    assert caplog.messages[0] == "Exception Bad Request while downloading favicon http://icon"
