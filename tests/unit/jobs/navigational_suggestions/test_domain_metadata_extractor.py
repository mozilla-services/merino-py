# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for domain_metadata_extractor.py module."""
from typing import Any, Optional

import pytest
from pytest_mock import MockerFixture

from merino.jobs.navigational_suggestions.domain_metadata_extractor import (
    DomainMetadataExtractor,
    FaviconData,
    Scraper,
)
from merino.jobs.navigational_suggestions.utils import FaviconDownloader, FaviconImage

FaviconScenario = tuple[
    FaviconData | None,
    list[FaviconImage] | None,
    list[tuple[int, int]] | None,
    str | None,
    list[dict[str, Any]],
    list[str],
]
TitleScenario = tuple[
    tuple[Optional[str], Optional[str]], list[dict[str, Any]], list[dict[str, str]]
]

FAVICON_SCENARIOS: list[FaviconScenario] = [
    (
        FaviconData(links=[], metas=[], url="https://www.google.com/"),
        [
            FaviconImage(content=b"\\x00", content_type="image/x-icon"),
        ],
        [(32, 32)],
        "https://google.com/favicon.ico",
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
            FaviconImage(content=b"\\x00", content_type="image/png"),
            FaviconImage(content=b"\\x01", content_type="image/svg+xml"),
        ],
        [(32, 32)],
        None,
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
    (
        FaviconData(
            links=[],
            metas=[
                {
                    "name": "apple-touch-icon",
                    "content": (
                        "https://assets.nflxext.com/en_us/layout/ecweb/"
                        "netflix-app-icon_152.jpg"
                    ),
                }
            ],
            url="https://www.netflix.com/",
        ),
        [
            FaviconImage(content=b"\\x00", content_type="image/jpg"),
        ],
        [(32, 32)],
        None,
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
    (
        None,
        None,
        None,
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
    (
        FaviconData(
            links=[
                {
                    "rel": ["icon"],
                    "type": "image/png",
                    "sizes": "192x192",
                    "href": (
                        "https://www.redditstatic.com/desktop2x/img/favicon/"
                        "android-icon-192x192.png"
                    ),
                },
            ],
            metas=[],
            url="https://www.reddit.com/",
        ),
        [
            FaviconImage(content=b"\\x00", content_type="image/png"),
        ],
        [(192, 192)],
        None,
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
    (
        FaviconData(
            links=[
                {
                    "rel": ["icon"],
                    "type": "image/x-icon",
                    "sizes": "any",
                    "href": "https://www.whitehouse.gov/favicon.ico",
                },
            ],
            metas=[],
            url="https://www.whitehouse.gov/",
        ),
        [
            FaviconImage(content=b"\\x00", content_type="image/x-icon"),
        ],
        [(32, 32)],
        None,
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
                    "rel": ["icon"],
                    "sizes": "any",
                    "mask": "",
                    "href": (
                        "//www.baidu.com/img/baidu_85beaf5496f291521eb75ba38eacbd87.svg"
                    ),
                },
            ],
            metas=[],
            url="https://www.baidu.com/",
        ),
        [
            FaviconImage(content=b"\\x00", content_type="image/svg+xml"),
        ],
        None,
        None,
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
        [""],
    ),
    (
        FaviconData(
            links=[
                {
                    "rel": ["icon"],
                    "type": "image/x-icon",
                    "sizes": "any",
                    "href": "data:favicon1.ico",
                },
            ],
            metas=[{"name": "apple-touch-icon", "content": "data:favicon2.ico"}],
            url="https://www.fakedomain.gov/",
        ),
        None,
        None,
        None,
        [
            {
                "rank": 272,
                "domain": "fakedomain.gov",
                "host": "www.fakedomain.gov",
                "origin": "https://www.fakedomain.gov",
                "suffix": "gov",
                "categories": ["Politics, Advocacy, and Government-Related"],
            }
        ],
        [""],
    ),
    (
        FaviconData(
            links=[
                {
                    "rel": ["icon"],
                    "type": "image/x-icon",
                    "sizes": "any",
                    "href": "favicon1.ico",
                },
            ],
            metas=[{"name": "apple-touch-icon", "content": "favicon2.ico"}],
            url="https://www.fakedomain.gov/",
        ),
        [
            FaviconImage(content=b"\\x00", content_type="image/x-icon"),
        ],
        [(64, 64), (32, 32)],
        None,
        [
            {
                "rank": 272,
                "domain": "fakedomain.gov",
                "host": "www.fakedomain.gov",
                "origin": "https://www.fakedomain.gov",
                "suffix": "gov",
                "categories": ["Politics, Advocacy, and Government-Related"],
            }
        ],
        ["https://www.fakedomain.gov/favicon1.ico"],
    ),
    (
        FaviconData(
            links=[
                {
                    "rel": ["icon"],
                    "type": "image/x-icon",
                    "href": "favicon1.ico",
                },
            ],
            metas=[],
            url="https://www.fakedomain.gov/",
        ),
        [
            FaviconImage(content=b"\\x00", content_type="image/x-icon"),
        ],
        [(16, 16)],
        None,
        [
            {
                "rank": 272,
                "domain": "fakedomain.gov",
                "host": "www.fakedomain.gov",
                "origin": "https://www.fakedomain.gov",
                "suffix": "gov",
                "categories": ["Politics, Advocacy, and Government-Related"],
            }
        ],
        [""],
    ),
]


@pytest.mark.parametrize(
    [
        "favicon_data",
        "favicon_images",
        "favicon_image_sizes",
        "default_favicon",
        "domains_data",
        "expected_favicons",
    ],
    FAVICON_SCENARIOS,
    ids=[
        "favicon_found_in_default_path",
        "favicon_found_via_link_tag",
        "favicon_found_via_meta_tag",
        "no_favicon",
        "favicon_with_size_in_right_format",
        "favicon_with_size_in_wrong_format",
        "masked_svg_favicon_skipped",
        "favicon_url_starting_with_data_skipped",
        "favicon_url_missing_scheme_handled",
        "low_resolution_favicon_skipped",
    ],
)
def test_get_favicons(
    mocker: MockerFixture,
    favicon_data: FaviconData | None,
    favicon_images: list[FaviconImage] | None,
    favicon_image_sizes: list[tuple[int, int]] | None,
    default_favicon: str | None,
    domains_data: list[dict[str, Any]],
    expected_favicons: list[str],
) -> None:
    """Test that DomainMetadataExtractor returns favicons as expected"""
    scraper_mock: Any = mocker.Mock(spec=Scraper)
    scraper_mock.scrape_favicon_data.return_value = favicon_data
    scraper_mock.get_default_favicon.return_value = default_favicon

    favicon_downloader_mock: Any = mocker.Mock(spec=FaviconDownloader)
    favicon_downloader_mock.download_favicon.side_effect = favicon_images

    images_mock = []
    for image_size in favicon_image_sizes or []:
        image_mock: Any = mocker.Mock()
        image_mock.size = image_size
        images_mock.append(image_mock)

    mocker.patch(
        "merino.jobs.navigational_suggestions.domain_metadata_extractor.Image"
    ).open.return_value.__enter__.side_effect = images_mock

    metadata_extractor: DomainMetadataExtractor = DomainMetadataExtractor(
        scraper=scraper_mock, favicon_downloader=favicon_downloader_mock
    )

    favicons: list[str] = metadata_extractor.get_favicons(domains_data, min_width=32)

    assert favicons == expected_favicons


TITLE_SCENARIOS: list[TitleScenario] = [
    (
        ("https://google.com", "Google"),
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
    (
        ("https://www.investing.com", None),
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
    (
        ("https://www.minecraft.net/en-us", "Minecraft"),
        [
            {
                "rank": 642,
                "domain": "minecraft.net",
                "host": "www.minecraft.net",
                "origin": "https://www.minecraft.net",
                "suffix": "net",
                "categories": ["Gaming", "Hobbies & Interests"],
            },
        ],
        [{"url": "https://www.minecraft.net", "title": "Minecraft"}],
    ),
]


@pytest.mark.parametrize(
    ["url_and_title", "domains_data", "expected_urls_and_titles"],
    TITLE_SCENARIOS,
    ids=["title_from_document", "title_not_from_document", "redirected_base_url"],
)
def test_get_urls_and_titles(
    mocker: MockerFixture,
    url_and_title: tuple[str, str],
    domains_data: list[dict[str, Any]],
    expected_urls_and_titles: list[dict[str, Optional[str]]],
):
    """Test that DomainMetadataExtractor returns titles as expected"""
    scraper_mock: Any = mocker.Mock(spec=Scraper)
    scraper_mock.scrape_url_and_title.return_value = url_and_title
    metadata_extractor: DomainMetadataExtractor = DomainMetadataExtractor(
        scraper=scraper_mock
    )

    urls_and_titles: list[
        dict[str, Optional[str]]
    ] = metadata_extractor.get_urls_and_titles(domains_data)

    assert urls_and_titles == expected_urls_and_titles


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

    metadata_extractor: DomainMetadataExtractor = DomainMetadataExtractor()
    second_level_domains: list[str] = metadata_extractor.get_second_level_domains(
        domains_data
    )

    assert second_level_domains == expected_second_level_domains
