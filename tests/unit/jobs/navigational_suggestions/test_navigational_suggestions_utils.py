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
    update_top_picks_with_firefox_favicons,
)


def test_update_top_picks_with_firefox_favicons_favicon_added_for_special_domains():
    """Test that top picks is updated with firefox favicon for special domains
    when scraped available to top picks
    """
    input_top_picks = {
        "domains": [
            {
                "rank": 1,
                "domain": "google",
                "categories": ["Search Engines"],
                "url": "https://www.google.com",
                "title": "Google",
                "icon": "",
            },
        ]
    }

    updated_top_picks = {
        "domains": [
            {
                "rank": 1,
                "domain": "google",
                "categories": ["Search Engines"],
                "url": "https://www.google.com",
                "title": "Google",
                "icon": (
                    "chrome://activity-stream/content/data/content/tippytop/"
                    "images/google-com@2x.png"
                ),
            },
        ]
    }

    update_top_picks_with_firefox_favicons(input_top_picks)
    assert input_top_picks == updated_top_picks


def test_update_top_picks_with_firefox_favicons_favicon_not_added_for_non_special_domains():
    """Test that top picks is not updated with firefox favicon for non special domains"""
    input_top_picks = {
        "domains": [
            {
                "rank": 2,
                "domain": "facebook",
                "categories": ["Social Networks"],
                "url": "https://www.facebook.com",
                "title": "Facebook \u2013 log in or sign up",
                "icon": "",
            },
        ]
    }

    updated_top_picks = {
        "domains": [
            {
                "rank": 2,
                "domain": "facebook",
                "categories": ["Social Networks"],
                "url": "https://www.facebook.com",
                "title": "Facebook \u2013 log in or sign up",
                "icon": "",
            },
        ]
    }

    update_top_picks_with_firefox_favicons(input_top_picks)
    assert input_top_picks == updated_top_picks


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
