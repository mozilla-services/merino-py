# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for utils.py module."""

import logging

from pytest import LogCaptureFixture
from pytest_mock import MockerFixture

from merino.jobs.navigational_suggestions.utils import (
    REQUEST_HEADERS,
    FaviconDownloader,
)


def test_favicon_downloader(requests_mock):
    """Test FaviconDownloader using requests_mock"""
    requests_mock.register_uri(
        "GET",
        "http://icon",
        request_headers=REQUEST_HEADERS,
        headers={"Content-Type": "image/x-icon"},
        content=b"1",
    )
    downloader = FaviconDownloader()
    favicon = downloader.download_favicon("http://icon")

    assert favicon is not None
    assert favicon.content == b"1"
    assert favicon.content_type == "image/x-icon"


def test_favicon_downloader_handles_exception(
    requests_mock, mocker: MockerFixture, caplog: LogCaptureFixture
):
    """Test FaviconDownloader using requests_mock"""
    caplog.set_level(logging.INFO)

    requests_mock.register_uri(
        "GET",
        "http://icon",
        request_headers=REQUEST_HEADERS,
        headers={"Content-Type": "image/x-icon"},
        content=b"1",
    )
    mocker.patch(
        "merino.jobs.navigational_suggestions.utils.requests_get",
        side_effect=Exception("Bad Request"),
    )
    downloader = FaviconDownloader()

    downloader.download_favicon("http://icon")

    assert len(caplog.messages) == 1
    assert caplog.messages[0] == "Exception Bad Request while downloading favicon http://icon"
