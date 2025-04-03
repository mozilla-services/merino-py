# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for utils.py module."""

import logging
import asyncio

import pytest
import httpx
from pytest import LogCaptureFixture
from pytest_mock import MockerFixture

from merino.jobs.navigational_suggestions.utils import (
    AsyncFaviconDownloader,
    REQUEST_HEADERS,
)
from merino.utils.gcs.models import Image


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


@pytest.mark.asyncio
async def test_download_multiple_favicons(mocker):
    """Test that download_multiple_favicons calls download_favicon for each URL"""
    # Create a mock favicon image
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
    assert len(caplog.messages) == 0


@pytest.mark.asyncio
async def test_download_favicon_with_invalid_content_type(mocker):
    """Test download_favicon with invalid content type."""
    # Create a mock response with non-image content type
    mock_response = mocker.AsyncMock()
    mock_response.status_code = 200
    mock_response.content = b"text content"
    mock_response.headers = {"Content-Type": "text/html"}

    # Create the session mock
    mock_session = mocker.AsyncMock()
    mock_session.get.return_value = mock_response

    # Create the downloader and set the session
    downloader = AsyncFaviconDownloader()
    downloader.session = mock_session

    # Test the method
    favicon = await downloader.download_favicon("http://example.com/favicon.ico")

    # Should still return an image with the content type from the response
    assert favicon is not None
    assert favicon.content == b"text content"
    assert favicon.content_type == "text/html"


@pytest.mark.asyncio
async def test_download_favicon_with_redirect(mocker):
    """Test download_favicon handles redirects."""
    # Create a mock response with non-image content type
    mock_response = mocker.AsyncMock()
    mock_response.status_code = 200
    mock_response.content = b"favicon content"
    mock_response.headers = {"Content-Type": "image/png"}
    mock_response.url = "http://example.com/redirected-favicon.ico"  # Redirected URL

    # Create the session mock
    mock_session = mocker.AsyncMock()
    mock_session.get.return_value = mock_response

    # Create the downloader and set the session
    downloader = AsyncFaviconDownloader()
    downloader.session = mock_session

    # Test the method
    favicon = await downloader.download_favicon("http://example.com/favicon.ico")

    # Should return the favicon with the redirected URL accessible
    assert favicon is not None
    assert favicon.content == b"favicon content"

    # Verify follow_redirects was used in the request
    mock_session.get.assert_called_once_with(
        "http://example.com/favicon.ico", headers=REQUEST_HEADERS, follow_redirects=True
    )


@pytest.mark.asyncio
async def test_download_multiple_favicons_with_semaphore(mocker):
    """Test that download_multiple_favicons uses a semaphore to limit concurrency."""
    # Create a mock for asyncio.Semaphore
    mock_semaphore = mocker.MagicMock()

    # Mock the __aenter__ and __aexit__ methods
    mock_semaphore.__aenter__ = mocker.AsyncMock()
    mock_semaphore.__aexit__ = mocker.AsyncMock()

    # Mock the Semaphore class to return our mock
    mocker.patch("asyncio.Semaphore", return_value=mock_semaphore)

    # Create a test favicon
    test_favicon = Image(content=b"test", content_type="image/png")

    # Create the downloader and mock download_favicon
    downloader = AsyncFaviconDownloader()

    mocker.patch.object(
        downloader, "download_favicon", new=mocker.AsyncMock(return_value=test_favicon)
    )

    # Test with multiple URLs
    urls = ["http://example1.com", "http://example2.com", "http://example3.com"]
    await downloader.download_multiple_favicons(urls)

    # Verify semaphore was used correctly
    assert asyncio.Semaphore.call_count == 1
    assert asyncio.Semaphore.call_args[0][0] == 5  # Semaphore(5)

    # Verify __aenter__ was called for each URL
    assert mock_semaphore.__aenter__.call_count == len(urls)

    # Verify __aexit__ was called for each URL
    assert mock_semaphore.__aexit__.call_count == len(urls)


@pytest.mark.asyncio
async def test_download_multiple_favicons_with_empty_list():
    """Test download_multiple_favicons with an empty URLs list."""
    downloader = AsyncFaviconDownloader()

    # Test with empty list
    results = await downloader.download_multiple_favicons([])

    # Should return an empty list
    assert results == []


@pytest.mark.asyncio
async def test_download_favicon_null_response(mocker):
    """Test download_favicon when requests_get returns None."""
    # Create the downloader
    downloader = AsyncFaviconDownloader()

    # Use mocker.AsyncMock instead of AsyncMock
    null_response = mocker.AsyncMock(return_value=None)

    # Patch the method
    mocker.patch.object(downloader, "requests_get", new=null_response)

    # Test the method
    favicon = await downloader.download_favicon("http://example.com/favicon.ico")

    # Should return None
    assert favicon is None


@pytest.mark.asyncio
async def test_download_favicon_with_timeout(mocker):
    """Test download_favicon timing out."""
    # Create a mock HTTP client that times out
    mock_session = mocker.MagicMock()
    mock_session.get = mocker.AsyncMock(side_effect=httpx.TimeoutException("Connection timed out"))

    # Create downloader and inject mock session
    downloader = AsyncFaviconDownloader()
    downloader.session = mock_session

    # Call download_favicon with a URL
    result = await downloader.download_favicon("https://example.com/favicon.ico")

    # Verify result is None
    assert result is None
    mock_session.get.assert_called_once_with(
        "https://example.com/favicon.ico", headers=REQUEST_HEADERS, follow_redirects=True
    )


@pytest.mark.asyncio
async def test_requests_get_with_non_200_status(mocker):
    """Test requests_get handling non-200 status codes."""
    # Create a mock response with non-200 status
    mock_response = mocker.MagicMock()
    mock_response.status_code = 404

    mock_session = mocker.MagicMock()
    mock_session.get = mocker.AsyncMock(return_value=mock_response)

    # Create downloader and inject mock session
    downloader = AsyncFaviconDownloader()
    downloader.session = mock_session

    # Call requests_get
    result = await downloader.requests_get("https://example.com/not-found")

    # Verify result is None for non-200 status
    assert result is None
    mock_session.get.assert_called_once_with(
        "https://example.com/not-found", headers=REQUEST_HEADERS, follow_redirects=True
    )


@pytest.mark.asyncio
async def test_download_multiple_favicons_with_exception_handling(mocker):
    """Test that download_multiple_favicons properly handles exceptions."""
    # Create a downloader
    downloader = AsyncFaviconDownloader()

    # Create a side effect that raises an exception for specific URLs
    async def download_with_error(url):
        if "error" in url:
            raise Exception("Test error")
        return Image(content=b"test image", content_type="image/png")

    # Mock the download_favicon method
    mocker.patch.object(downloader, "download_favicon", side_effect=download_with_error)

    # Create a list of URLs, one of which will cause an error
    urls = [
        "https://example.com/favicon.ico",
        "https://example.com/error-favicon.ico",
        "https://example.com/logo.png",
    ]

    # Call the method
    results = await downloader.download_multiple_favicons(urls)

    # Verify we got 3 results (none are lost despite the error)
    assert len(results) == 3

    # First and last should be images, middle should be None due to error
    assert isinstance(results[0], Image)
    assert results[1] is None
    assert isinstance(results[2], Image)

    # Verify all URLs were attempted
    assert downloader.download_favicon.call_count == 3
