# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# TODO DISCO-2359 (Required) Re-categorize this module as unit tests
"""Integration tests for domain_metadata_extractor.py module."""
from typing import Any

import pytest
from pytest_mock import MockerFixture

from merino.jobs.navigational_suggestions.domain_metadata_extractor import (
    DomainMetadataExtractor,
    FaviconData,
    Scraper,
)

FaviconScenario = tuple[FaviconData | None, list[dict[str, Any]], list[str]]
TitleScenario = tuple[str | None, list[dict[str, Any]], list[dict[str, str]]]

FAVICON_SCENARIOS: list[FaviconScenario] = [
    # Non-svg favicon
    (
        FaviconData(links=[], metas=[], url="https://www.google.com/"),
        [
            {
                "rank": 1,
                "domain": "google.com",
                "host": "one.google.com",
                "origin": "https://one.google.com",
                "suffix": "com",
                "categories": ["Search Engines"],
            },
        ],
        ["https://google.com/favicon.ico"],
    ),
    # svg favicon
    (
        FaviconData(
            links=[
                {
                    "rel": ["fluid-icon"],
                    "href": "https://github.com/fluidicon.png",
                    "title": "GitHub",
                },
                {
                    "rel": ["icon"],
                    "class": ["js-site-favicon"],
                    "type": "image/svg+xml",
                    "href": "https://github.githubassets.com/favicons/favicon.svg",
                },
            ],
            metas=[],
            url="https://github.com/",
        ),
        [
            {
                "rank": 23,
                "domain": "github.com",
                "host": "github.com",
                "origin": "https://github.com",
                "suffix": "com",
                "categories": ["Technology"],
            },
        ],
        ["https://github.githubassets.com/favicons/favicon.svg"],
    ),
    # Empty icon because domain unreachable
    (
        None,
        [
            {
                "rank": 4,
                "domain": "amazonaws.com",
                "host": "lsrelay-config-production.s3.amazonaws.com",
                "origin": "http://lsrelay-config-production.s3.amazonaws.com",
                "suffix": "com",
                "categories": ["Technology"],
            },
        ],
        [""],
    ),
    # Domain with a valid favicon size specified via 'sizes' attribute
    (
        FaviconData(
            links=[
                {
                    "rel": ["apple-touch-icon"],
                    "sizes": "57x57",
                    "href": (
                        "https://www.redditstatic.com/desktop2x/img/favicon/"
                        "apple-icon-57x57.png"
                    ),
                },
                {
                    "rel": ["apple-touch-icon"],
                    "sizes": "60x60",
                    "href": (
                        "https://www.redditstatic.com/desktop2x/img/favicon/"
                        "apple-icon-60x60.png"
                    ),
                },
                {
                    "rel": ["apple-touch-icon"],
                    "sizes": "72x72",
                    "href": (
                        "https://www.redditstatic.com/desktop2x/img/favicon/"
                        "apple-icon-72x72.png"
                    ),
                },
                {
                    "rel": ["apple-touch-icon"],
                    "sizes": "76x76",
                    "href": (
                        "https://www.redditstatic.com/desktop2x/img/favicon/"
                        "apple-icon-76x76.png"
                    ),
                },
                {
                    "rel": ["apple-touch-icon"],
                    "sizes": "114x114",
                    "href": (
                        "https://www.redditstatic.com/desktop2x/img/favicon/"
                        "apple-icon-114x114.png"
                    ),
                },
                {
                    "rel": ["apple-touch-icon"],
                    "sizes": "120x120",
                    "href": (
                        "https://www.redditstatic.com/desktop2x/img/favicon/"
                        "apple-icon-120x120.png"
                    ),
                },
                {
                    "rel": ["apple-touch-icon"],
                    "sizes": "144x144",
                    "href": (
                        "https://www.redditstatic.com/desktop2x/img/favicon/"
                        "apple-icon-144x144.png"
                    ),
                },
                {
                    "rel": ["apple-touch-icon"],
                    "sizes": "152x152",
                    "href": (
                        "https://www.redditstatic.com/desktop2x/img/favicon/"
                        "apple-icon-152x152.png"
                    ),
                },
                {
                    "rel": ["apple-touch-icon"],
                    "sizes": "180x180",
                    "href": (
                        "https://www.redditstatic.com/desktop2x/img/favicon/"
                        "apple-icon-180x180.png"
                    ),
                },
                {
                    "rel": ["icon"],
                    "type": "image/png",
                    "sizes": "192x192",
                    "href": (
                        "https://www.redditstatic.com/desktop2x/img/favicon/"
                        "android-icon-192x192.png"
                    ),
                },
                {
                    "rel": ["icon"],
                    "type": "image/png",
                    "sizes": "32x32",
                    "href": (
                        "https://www.redditstatic.com/desktop2x/img/favicon/"
                        "favicon-32x32.png"
                    ),
                },
                {
                    "rel": ["icon"],
                    "type": "image/png",
                    "sizes": "96x96",
                    "href": (
                        "https://www.redditstatic.com/desktop2x/img/favicon/"
                        "favicon-96x96.png"
                    ),
                },
                {
                    "rel": ["icon"],
                    "type": "image/png",
                    "sizes": "16x16",
                    "href": (
                        "https://www.redditstatic.com/desktop2x/img/favicon/"
                        "favicon-16x16.png"
                    ),
                },
            ],
            metas=[],
            url="https://www.reddit.com/",
        ),
        [
            {
                "rank": 24,
                "domain": "reddit.com",
                "host": "old.reddit.com",
                "origin": "https://old.reddit.com",
                "suffix": "com",
                "categories": ["Forums"],
            }
        ],
        ["https://www.redditstatic.com/desktop2x/img/favicon/android-icon-192x192.png"],
    ),
    # Domain with an invalid favicon size specified via 'sizes' attribute
    (
        FaviconData(
            links=[
                {
                    "rel": ["icon"],
                    "type": "image/x-icon",
                    "sizes": "any",
                    "href": "https://www.whitehouse.gov/favicon.ico",
                },
                {
                    "rel": ["icon"],
                    "type": "image/png",
                    "sizes": "32x32",
                    "href": (
                        "https://www.whitehouse.gov/wp-content/images/favicon-32x32.png"
                    ),
                },
                {
                    "rel": ["icon"],
                    "type": "image/png",
                    "sizes": "16x16",
                    "href": (
                        "https://www.whitehouse.gov/wp-content/images/favicon-16x16.png"
                    ),
                },
                {
                    "rel": ["apple-touch-icon"],
                    "sizes": "180x180",
                    "href": (
                        "https://www.whitehouse.gov/wp-content/images/"
                        "apple-touch-icon.png"
                    ),
                },
            ],
            metas=[],
            url="https://www.whitehouse.gov/",
        ),
        [
            {
                "rank": 272,
                "domain": "whitehouse.gov",
                "host": "www.whitehouse.gov",
                "origin": "https://www.whitehouse.gov",
                "suffix": "gov",
                "categories": ["Politics, Advocacy, and Government-Related"],
            }
        ],
        ["https://www.whitehouse.gov/favicon.ico"],
    ),
    (
        FaviconData(
            links=[
                {
                    "rel": ["shortcut", "icon"],
                    "href": "https://www.baidu.com/favicon.ico",
                    "type": "image/x-icon",
                },
                {
                    "rel": ["icon"],
                    "sizes": "any",
                    "mask": "",
                    "href": (
                        "//www.baidu.com/img/baidu_85beaf5496f291521eb75ba38eacbd87.svg"
                    ),
                },
                {
                    "rel": ["apple-touch-icon-precomposed"],
                    "href": (
                        "https://psstatic.cdn.bcebos.com/video/wiseindex/"
                        "aa6eef91f8b5b1a33b454c401_1660835115000.png"
                    ),
                },
            ],
            metas=[],
            url="https://www.baidu.com/",
        ),
        [
            {
                "rank": 8,
                "domain": "baidu.com",
                "host": "www.baidu.com",
                "origin": "https://www.baidu.com",
                "suffix": "com",
                "categories": ["Search Engines"],
            }
        ],
        [
            (
                "https://psstatic.cdn.bcebos.com/video/wiseindex/"
                "aa6eef91f8b5b1a33b454c401_1660835115000.png"
            )
        ],
    ),
    # Domain with favicons in meta tag
    (
        FaviconData(
            links=[
                {
                    "rel": ["shortcut", "icon"],
                    "href": (
                        "https://assets.nflxext.com/us/ffe/siteui/common/icons/"
                        "nficon2016.ico"
                    ),
                },
                {
                    "rel": ["apple-touch-icon"],
                    "href": (
                        "https://assets.nflxext.com/us/ffe/siteui/common/icons/"
                        "nficon2016.png"
                    ),
                },
                {
                    "name": "apple-touch-icon",
                    "content": (
                        "https://assets.nflxext.com/en_us/layout/ecweb/"
                        "netflix-app-icon_152.jpg"
                    ),
                    "href": (
                        "https://assets.nflxext.com/en_us/layout/ecweb/"
                        "netflix-app-icon_152.jpg"
                    ),
                },
            ],
            metas=[
                {
                    "name": "apple-touch-icon",
                    "content": (
                        "https://assets.nflxext.com/en_us/layout/ecweb/"
                        "netflix-app-icon_152.jpg"
                    ),
                }
            ],
            url="https://www.netflix.com/ca/",
        ),
        [
            {
                "rank": 6,
                "domain": "netflix.com",
                "host": "www.netflix.com",
                "origin": "https://www.netflix.com",
                "suffix": "com",
                "categories": ["Television", "Video Streaming", "Movies"],
            }
        ],
        ["https://assets.nflxext.com/en_us/layout/ecweb/netflix-app-icon_152.jpg"],
    ),
    # domain not satisfying min width criteria of favicon
    (
        FaviconData(links=[], metas=[], url="https://www.xbox.com:443/en-US/"),
        [
            {
                "rank": 396,
                "domain": "xbox.com",
                "host": "www.xbox.com",
                "origin": "https://www.xbox.com",
                "suffix": "com",
                "categories": ["Gaming"],
            }
        ],
        [""],
    ),
]


# TODO DISCO-2359 (Required) Remove reliance on external network request (mock requests)
@pytest.mark.xfail(reason="Test Flake Detected (ref: DISCO-2359)")
@pytest.mark.parametrize(
    ["favicon_data", "domains_data", "expected_favicons"],
    FAVICON_SCENARIOS
    # TODO DISCO-2359 (Optional) Use the 'ids' field to communicate test cases at
    #                            report level
)
def test_get_favicons(
    mocker: MockerFixture,
    favicon_data: FaviconData | None,
    domains_data: list[dict],
    expected_favicons: list[str],
) -> None:
    """Test that DomainMetadataExtractor returns favicons as expected"""
    scraper_mock: Any = mocker.Mock(spec=Scraper)
    scraper_mock.scrape_favicon_data.return_value = favicon_data
    metadata_extractor: DomainMetadataExtractor = DomainMetadataExtractor(
        scraper=scraper_mock
    )

    favicons: list[str] = metadata_extractor.get_favicons(domains_data, min_width=16)

    assert favicons == expected_favicons


TITLE_SCENARIOS: list[TitleScenario] = [
    # title extracted from document
    (
        "Google",
        [
            {
                "rank": 1,
                "domain": "google.com",
                "host": "one.google.com",
                "origin": "https://one.google.com",
                "suffix": "com",
                "categories": ["Search Engines"],
            },
        ],
        [{"url": "https://google.com", "title": "Google"}],
    ),
    # title as second level domain name as title scraping failed
    (
        None,
        [
            {
                "rank": 291,
                "domain": "investing.com",
                "host": "www.investing.com",
                "origin": "https://www.investing.com",
                "suffix": "com",
                "categories": ["Economy & Finance"],
            },
        ],
        [{"url": "https://www.investing.com", "title": "Investing"}],
    ),
    # title as second level domain name because domain unreachable
    (
        None,
        [
            {
                "rank": 4,
                "domain": "amazonaws.com",
                "host": "lsrelay-config-production.s3.amazonaws.com",
                "origin": "http://lsrelay-config-production.s3.amazonaws.com",
                "suffix": "com",
                "categories": ["Technology"],
            },
        ],
        [{"url": "https://www.amazonaws.com", "title": "Amazonaws"}],
    ),
]


@pytest.mark.parametrize(
    ["title", "domains_data", "expected_urls_and_titles"],
    TITLE_SCENARIOS,
    # TODO DISCO-2359 (Optional) Use the 'ids' field to communicate test cases at
    #                            report level
)
def test_get_urls_and_titles(
    mocker: MockerFixture,
    title: str,
    domains_data: list[dict],
    expected_urls_and_titles: list[dict[str, str]],
):
    """Test that DomainMetadataExtractor returns titles as expected"""
    # TODO DISCO-2359 (Optional) Add type annotations
    scraper_mock: Any = mocker.Mock(spec=Scraper)
    scraper_mock.scrape_title.return_value = title
    metadata_extractor = DomainMetadataExtractor(scraper=scraper_mock)

    urls_and_titles = metadata_extractor.get_urls_and_titles(domains_data)

    assert urls_and_titles == expected_urls_and_titles


def test_get_second_level_domains():
    """Test that DomainMetadataExtractor returns second level domain as expected"""
    # TODO DISCO-2359 (Optional) Add type annotations
    domains_data = [
        {
            "rank": 1,
            "domain": "google.com",
            "host": "one.google.com",
            "origin": "https://one.google.com",
            "suffix": "com",
            "categories": ["Search Engines"],
        },
        {
            "rank": 23,
            "domain": "github.com",
            "host": "github.com",
            "origin": "https://github.com",
            "suffix": "com",
            "categories": ["Technology"],
        },
    ]
    expected_second_level_domains = ["google", "github"]

    metadata_extractor = DomainMetadataExtractor()
    second_level_domains = metadata_extractor.get_second_level_domains(domains_data)

    assert second_level_domains == expected_second_level_domains
