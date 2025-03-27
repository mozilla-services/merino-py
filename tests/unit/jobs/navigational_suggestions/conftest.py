# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Fixtures for navigational_suggestions tests."""

import httpx
from typing import Dict

import pytest

from merino.jobs.navigational_suggestions.utils import AsyncFaviconDownloader


@pytest.fixture
def mock_async_response(mocker):
    """Create a mock async response with customizable attributes.

    This fixture creates a mock response that can be used in tests requiring
    HTTP response simulation for async context managers.

    Args:
        mocker: The pytest-mock fixture

    Returns:
        A factory function that creates custom mock responses
    """

    def _create_mock_response(
        status: int = 200,
        headers: Dict[str, str] | None = None,
        content: bytes = b"",
    ):
        """Create a mock response with the given attributes."""
        if headers is None:
            headers = {"Content-Type": "application/json"}

        # Create the mock response
        mock_response = mocker.MagicMock()
        mock_response.status = status
        mock_response.status_code = status
        mock_response.headers = headers
        mock_response.content = content
        mock_response.read = mocker.AsyncMock(return_value=content)

        return mock_response

    return _create_mock_response


@pytest.fixture
def mock_async_client_session(mocker, mock_async_response):
    """Create a mock httpx.AsyncClient with customizable response.

    This fixture allows tests to easily mock the httpx.AsyncClient
    for async HTTP requests, with configurable responses.

    Args:
        mocker: The pytest-mock fixture
        mock_async_response: The response factory fixture

    Returns:
        A factory function that creates a mock client session
    """

    def _create_mock_session(
        status: int = 200,
        headers: Dict[str, str] | None = None,
        content: bytes = b"",
    ):
        """Create a mock session with the given response attributes."""
        # Create the response using the other fixture
        response = mock_async_response(status, headers, content)
        response.status_code = status
        response.content = content

        # Create the session
        mock_session = mocker.MagicMock(spec=httpx.AsyncClient)
        mock_session.get = mocker.AsyncMock(return_value=response)

        return mock_session

    return _create_mock_session


@pytest.fixture
def mock_favicon_downloader(mocker, mock_async_client_session):
    """Create a pre-configured AsyncFaviconDownloader with mocked session.

    This fixture provides a ready-to-use AsyncFaviconDownloader with
    a mocked session for testing.

    Args:
        mocker: The pytest-mock fixture
        mock_async_client_session: The session factory fixture

    Returns:
        A factory function that creates a configured downloader
    """

    def _create_downloader(
        status: int = 200,
        content_type: str = "image/x-icon",
        content: bytes = b"1",
    ):
        """Create a downloader with the given response configuration."""
        # Create a session with the specified response
        headers = {"Content-Type": content_type}
        mock_session = mock_async_client_session(status, headers, content)

        # Create and configure the downloader
        downloader = AsyncFaviconDownloader()
        # Override the session with our mock
        downloader.session = mock_session

        return downloader

    return _create_downloader


@pytest.fixture
def mock_domain_metadata_uploader(mocker):
    """Create a mock DomainMetadataUploader for testing."""
    uploader = mocker.MagicMock()

    uploader.upload_image.return_value = "https://cnd.mozilla.com/uploaded-favicon.ico"
    uploader.destination_favicon_name.return_value = "favicons/12345_100.ico"

    return uploader
