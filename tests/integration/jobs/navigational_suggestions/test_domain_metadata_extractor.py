# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Integration tests for domain_metadata_extractor.py module."""

import pytest

from merino.jobs.navigational_suggestions.domain_metadata_extractor import (
    DomainMetadataExtractor,
)

Scenario = tuple[list[dict], list[str]]

FAVICON_SCENARIOS: list[Scenario] = [
    # Non-svg favicon
    (
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


@pytest.mark.xfail(reason="Test Flake Detected (ref: DISCO-2359)")
@pytest.mark.parametrize(
    ["domains_data", "expected_favicons"],
    FAVICON_SCENARIOS,
)
def test_get_favicons(domains_data: list[dict], expected_favicons: list[str]):
    """Test that DomainMetadataExtractor returns favicons as expected"""
    metadata_extractor = DomainMetadataExtractor()
    favicons = metadata_extractor.get_favicons(domains_data, min_width=16)
    assert len(favicons) == len(domains_data)
    for idx, favicon in enumerate(favicons):
        assert favicon == expected_favicons[idx]


TITLE_SCENARIOS: list[Scenario] = [
    # title extracted from document
    (
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
        ["Google"],
    ),
    # title as second level domain name as title scraping failed
    (
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
        ["Investing"],
    ),
    # title as second level domain name because domain unreachable
    (
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
        ["Amazonaws"],
    ),
]


@pytest.mark.parametrize(
    ["domains_data", "expected_titles"],
    TITLE_SCENARIOS,
)
def test_get_urls_and_titles(domains_data: list[dict], expected_titles: list[str]):
    """Test that DomainMetadataExtractor returns titles as expected"""
    metadata_extractor = DomainMetadataExtractor()
    urls_and_titles = metadata_extractor.get_urls_and_titles(domains_data)
    assert len(urls_and_titles) == len(domains_data)
    for idx, url_and_title in enumerate(urls_and_titles):
        assert url_and_title["title"] == expected_titles[idx]


def test_get_second_level_domains():
    """Test that DomainMetadataExtractor returns second level domain as expected"""
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

    assert len(second_level_domains) == len(domains_data)
    for idx, second_level_domain in enumerate(second_level_domains):
        assert second_level_domain == expected_second_level_domains[idx]
