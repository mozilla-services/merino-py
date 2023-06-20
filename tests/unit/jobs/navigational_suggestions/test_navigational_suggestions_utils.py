# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for utils.py module."""

from merino.jobs.navigational_suggestions.utils import (
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
