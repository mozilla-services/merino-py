# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for domain_metadata_extractor.py module."""
from typing import Any

import pytest
from pytest_mock import MockerFixture

from merino.content_handler.models import Image
from merino.jobs.navigational_suggestions.domain_metadata_extractor import (
    DomainMetadataExtractor,
    FaviconData,
    Scraper,
)
from merino.jobs.navigational_suggestions.utils import FaviconDownloader

DomainMetadataScenario = tuple[
    FaviconData | None,
    list[dict[str, Any]],
    list[Image] | None,
    list[tuple[int, int]] | None,
    str | None,
    str | None,
    str | None,
    list[dict[str, Any]],
    list[dict[str, str | None]],
]

DOMAIN_METADATA_SCENARIOS: list[DomainMetadataScenario] = [
    (
        FaviconData(links=[], metas=[], manifests=[]),
        [],
        [
            Image(content=b"\\x00", content_type="image/x-icon"),
        ],
        [(32, 32)],
        "https://google.com/favicon.ico",
        "https://www.google.com",
        "dummy_title",
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
        [
            {
                "url": "https://www.google.com",
                "title": "dummy_title",
                "icon": "https://google.com/favicon.ico",
                "domain": "google",
            }
        ],
    ),
    (
        FaviconData(
            links=[
                {
                    "rel": ["fluid-icon"],
                    "href": "https://github.com/fluidicon.png",
                    "title": "GitHub",
                },
            ],
            metas=[],
            manifests=[],
        ),
        [],
        [
            Image(content=b"\\x00", content_type="image/png"),
        ],
        [(32, 32)],
        None,
        "https://github.com/",
        "dummy_title",
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
        [
            {
                "url": "https://github.com",
                "title": "dummy_title",
                "icon": "https://github.com/fluidicon.png",
                "domain": "github",
            }
        ],
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
            manifests=[],
        ),
        [],
        [
            Image(content=b"\\x00", content_type="image/jpg"),
        ],
        [(32, 32)],
        None,
        "https://www.netflix.com/",
        "dummy_title",
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
        [
            {
                "url": "https://www.netflix.com",
                "title": "dummy_title",
                "icon": "https://assets.nflxext.com/en_us/layout/ecweb/netflix-app-icon_152.jpg",
                "domain": "netflix",
            }
        ],
    ),
    (
        FaviconData(
            links=[],
            metas=[],
            manifests=[
                {
                    "rel": ["manifest"],
                    "href": "/data/manifest/",
                    "crossorigin": "use-credentials",
                }
            ],
        ),
        [
            {
                "src": "https://static.xx.fbcdn.net/rsrc.php/v3/ya/r/hsAgIHTE80C.png",
                "sizes": "192x192",
                "type": "image/png",
            }
        ],
        [
            Image(content=b"\\x00", content_type="image/jpg"),
        ],
        [(32, 32)],
        None,
        "https://www.facebook.com/",
        "dummy_title",
        [
            {
                "rank": 2,
                "domain": "facebook.com",
                "host": "m.facebook.com",
                "origin": "https://m.facebook.com",
                "suffix": "com",
                "categories": ["Social Networks"],
            },
        ],
        [
            {
                "url": "https://www.facebook.com",
                "title": "dummy_title",
                "icon": "https://static.xx.fbcdn.net/rsrc.php/v3/ya/r/hsAgIHTE80C.png",
                "domain": "facebook",
            }
        ],
    ),
    (
        None,
        [],
        None,
        None,
        None,
        "https://www.amazonaws.com",
        "dummy_title",
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
        [
            {
                "url": "https://www.amazonaws.com",
                "title": "dummy_title",
                "icon": "",
                "domain": "amazonaws",
            }
        ],
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
            manifests=[],
        ),
        [],
        [
            Image(content=b"\\x00", content_type="image/svg+xml"),
        ],
        None,
        None,
        "https://www.baidu.com/",
        "dummy_title",
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
            {
                "url": "https://www.baidu.com",
                "title": "dummy_title",
                "icon": "",
                "domain": "baidu",
            }
        ],
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
            manifests=[],
        ),
        [],
        [
            Image(content=b"\\x00", content_type="image/png"),
            Image(content=b"\\x01", content_type="image/svg+xml"),
        ],
        [(32, 32)],
        None,
        "https://github.com/",
        "dummy_title",
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
        [
            {
                "url": "https://github.com",
                "title": "dummy_title",
                "icon": "https://github.githubassets.com/favicons/favicon.svg",
                "domain": "github",
            }
        ],
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
            manifests=[],
        ),
        [],
        None,
        None,
        None,
        "https://www.fakedomain.gov/",
        "dummy_title",
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
        [
            {
                "url": "https://www.fakedomain.gov",
                "title": "dummy_title",
                "icon": "",
                "domain": "fakedomain",
            }
        ],
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
            manifests=[],
        ),
        [],
        [
            Image(content=b"\\x00", content_type="image/x-icon"),
            Image(content=b"\\x01", content_type="image/x-icon"),
        ],
        [(64, 64), (32, 32)],
        None,
        "https://www.fakedomain.gov/",
        "dummy_title",
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
        [
            {
                "url": "https://www.fakedomain.gov",
                "title": "dummy_title",
                "icon": "https://www.fakedomain.gov/favicon1.ico",
                "domain": "fakedomain",
            }
        ],
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
            manifests=[],
        ),
        [],
        [
            Image(content=b"\\x00", content_type="image/x-icon"),
        ],
        [(16, 16)],
        None,
        "https://www.fakedomain.gov/",
        "dummy_title",
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
        [
            {
                "url": "https://www.fakedomain.gov",
                "title": "dummy_title",
                "icon": "",
                "domain": "fakedomain",
            }
        ],
    ),
    (
        FaviconData(
            links=[
                {
                    "rel": ["icon"],
                    "type": "image/png",
                    "href": "https://www.researchgate.net/favicon-96x96.png",
                    "sizes": "96x96",
                },
            ],
            metas=[],
            manifests=[],
        ),
        [],
        [
            Image(content=b"\\x00", content_type="text/html"),
        ],
        [(96, 96)],
        None,
        "https://www.researchgate.net/",
        "dummy_title",
        [
            {
                "rank": 84,
                "domain": "researchgate.net",
                "host": "www.researchgate.net",
                "origin": "https://www.researchgate.net",
                "suffix": "net",
                "categories": ["Education"],
            }
        ],
        [
            {
                "url": "https://www.researchgate.net",
                "title": "dummy_title",
                "icon": "",
                "domain": "researchgate",
            }
        ],
    ),
    (
        None,
        [],
        None,
        None,
        None,
        "https://www.investing.com",
        None,
        [
            {
                "rank": 291,
                "domain": "investing.com",
                "host": "www.investing.com",
                "origin": "https://www.investing.com",
                "suffix": "com",
                "categories": ["Economy & Finance"],
            }
        ],
        [
            {
                "url": "https://www.investing.com",
                "title": "Investing",
                "icon": "",
                "domain": "investing",
            }
        ],
    ),
    (
        None,
        [],
        None,
        None,
        None,
        "https://aws.amazon.com/",
        "dummy_title",
        [
            {
                "rank": 4,
                "domain": "amazonaws.com",
                "host": "lsrelay-config-production.s3.amazonaws.com",
                "origin": "http://lsrelay-config-production.s3.amazonaws.com",
                "suffix": "com",
                "categories": ["Technology"],
            }
        ],
        [
            {
                "url": None,
                "title": "",
                "icon": "",
                "domain": "",
            }
        ],
    ),
    (
        None,
        [],
        None,
        None,
        None,
        None,
        "dummy_title",
        [
            {
                "rank": 4,
                "domain": "amazonaws.com",
                "host": "lsrelay-config-production.s3.amazonaws.com",
                "origin": "http://lsrelay-config-production.s3.amazonaws.com",
                "suffix": "com",
                "categories": ["Technology"],
            }
        ],
        [
            {
                "url": None,
                "title": "",
                "icon": "",
                "domain": "",
            }
        ],
    ),
    (
        FaviconData(links=[], metas=[], manifests=[]),
        [],
        [
            Image(content=b"\\x00", content_type="image/x-icon"),
        ],
        [(32, 32)],
        "https://foo.eu/favicon.ico",
        "https://foo.eu",
        "dummy_title",
        [
            {
                "rank": 821,
                "domain": "foo.eu",
                "host": "foo.eu",
                "origin": "https://foo.eu",
                "suffix": "eu",
                "categories": ["Food & Drink"],
            },
        ],
        [
            {
                "url": None,
                "title": "",
                "icon": "",
                "domain": "",
            }
        ],
    ),
]


@pytest.fixture(name="domain_blocklist")
def fixture_domain_blocklist() -> set[str]:
    """Domain blocklist fixture."""
    return {"foo", "bar"}


@pytest.mark.parametrize(
    [
        "favicon_data",
        "scraped_favicons_from_manifest",
        "favicon_images",
        "favicon_image_sizes",
        "default_favicon",
        "scraped_url",
        "scraped_title",
        "domains_data",
        "expected_domain_metadata",
    ],
    DOMAIN_METADATA_SCENARIOS,
    ids=[
        "favicon_found_in_default_path",
        "favicon_found_via_link_tag",
        "favicon_found_via_meta_tag",
        "favicon_found_via_manifest",
        "no_favicon",
        "masked_svg_favicon_skipped",
        "favicon_always_non_masked_svg_favicon_when_present",
        "favicon_url_starting_with_data_skipped",
        "favicon_url_missing_scheme_handled",
        "low_resolution_favicon_skipped",
        "favicon_with_non_image_mime_type_skipped",
        "title_not_from_document",
        "url_not_containing_domain_skipped",
        "unreachable_url_skipped",
        "blocked_domain_skipped",
    ],
)
def test_get_domain_metadata(
    mocker: MockerFixture,
    favicon_data: FaviconData | None,
    scraped_favicons_from_manifest: list[dict[str, Any]],
    favicon_images: list[Image] | None,
    favicon_image_sizes: list[tuple[int, int]] | None,
    default_favicon: str | None,
    scraped_url: str | None,
    scraped_title: str | None,
    domains_data: list[dict[str, Any]],
    expected_domain_metadata: list[str],
    domain_blocklist: set[str],
) -> None:
    """Test that DomainMetadataExtractor returns favicons as expected"""
    scraper_mock: Any = mocker.Mock(spec=Scraper)
    scraper_mock.scrape_favicon_data.return_value = favicon_data
    scraper_mock.scrape_favicons_from_manifest.return_value = (
        scraped_favicons_from_manifest
    )
    scraper_mock.get_default_favicon.return_value = default_favicon
    scraper_mock.open.return_value = scraped_url
    scraper_mock.scrape_title.return_value = scraped_title

    favicon_downloader_mock: Any = mocker.Mock(spec=FaviconDownloader)
    favicon_downloader_mock.download_favicon.side_effect = favicon_images

    # mock the PIL module's Image.open method in our custom Image model
    mocker.patch(
        "merino.content_handler.models.PILImage.open"
    ).side_effect = favicon_image_sizes

    metadata_extractor: DomainMetadataExtractor = DomainMetadataExtractor(
        blocked_domains=domain_blocklist,
        scraper=scraper_mock,
        favicon_downloader=favicon_downloader_mock,
    )

    domain_metadata: list[
        dict[str, str | None]
    ] = metadata_extractor.get_domain_metadata(domains_data, favicon_min_width=32)

    assert domain_metadata == expected_domain_metadata
