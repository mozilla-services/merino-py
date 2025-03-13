# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for __init__.py module."""

import json

from merino.jobs.navigational_suggestions import prepare_domain_metadata
from merino.providers.suggest.base import Category


def test_prepare_domain_metadata_top_picks_construction(mocker):
    """Test whether top pick is constructed properly"""
    mock_domain_data_downloader = mocker.patch(
        "merino.jobs.navigational_suggestions.DomainDataDownloader"
    ).return_value
    mock_domain_metadata_extractor = mocker.patch(
        "merino.jobs.navigational_suggestions.DomainMetadataExtractor"
    ).return_value
    mock_domain_metadata_uploader = mocker.patch(
        "merino.jobs.navigational_suggestions.DomainMetadataUploader"
    ).return_value

    # Mock the GCS Uploader
    mocker.patch("merino.jobs.navigational_suggestions.GcsUploader").return_value

    mock_domain_data_downloader.download_data.return_value = [
        {
            "rank": 1,
            "domain": "dummy_domain.com",
            "host": "www.dummy_domain.com",
            "origin": "https://www.dummy_domain.com",
            "suffix": "com",
            "categories": ["Search Engines"],
        },
        {
            "rank": 2,
            "domain": "dummy_unreachable_domain.com",
            "host": "www.dummy_unreachable_domain.com",
            "origin": "https://www.dummy_unreachable_domain.com",
            "suffix": "com",
            "categories": ["Search Engines"],
        },
    ]

    mock_domain_metadata_extractor.get_domain_metadata.return_value = [
        {
            "url": "dummy_url.com",
            "title": "dummy_title",
            "icon": "dummy_icon",
            "domain": "dummy_domain",
        },
        {"url": None, "title": "", "icon": "", "domain": ""},
    ]

    mocker.patch("merino.jobs.navigational_suggestions._construct_partner_manifest").return_value

    mock_domain_metadata_uploader.upload_favicons.return_value = [
        "dummy_uploaded_favicon_url",
        "",
    ]

    mock_domain_metadata_uploader.compare_top_picks.return_value = (
        ["Search Engines"],
        {"dummy_domain"},
        {},
        {},
        [],
    )

    mock_domain_metadata_uploader._get_serp_categories.return_value = Category.Inconclusive

    prepare_domain_metadata(
        "dummy_src_project", "dummy_destination_project", "dummy_destination_blob"
    )

    expected_top_picks = {
        "domains": [
            {
                "rank": 1,
                "domain": "dummy_domain",
                "categories": ["Search Engines"],
                "serp_categories": [0],
                "url": "dummy_url.com",
                "title": "dummy_title",
                "icon": "dummy_uploaded_favicon_url",
            }
        ]
    }
    mock_domain_metadata_uploader.upload_top_picks.assert_called_once_with(
        json.dumps(expected_top_picks, indent=4)
    )


def test_prepare_domain_metadata_partner_manifest(mocker):
    """Test whether the partner manifest is constructed properly and exists in the final top picks result"""
    mock_domain_data_downloader = mocker.patch(
        "merino.jobs.navigational_suggestions.DomainDataDownloader"
    ).return_value
    mock_domain_metadata_extractor = mocker.patch(
        "merino.jobs.navigational_suggestions.DomainMetadataExtractor"
    ).return_value
    mock_domain_metadata_uploader = mocker.patch(
        "merino.jobs.navigational_suggestions.DomainMetadataUploader"
    ).return_value
    mocker.patch("merino.jobs.navigational_suggestions.GcsUploader").return_value

    mock_domain_data_downloader.download_data.return_value = [
        {
            "rank": 1,
            "domain": "dummy_domain.com",
            "host": "www.dummy_domain.com",
            "origin": "https://www.dummy_domain.com",
            "suffix": "com",
            "categories": ["Search Engines"],
        }
    ]

    mock_domain_metadata_extractor.get_domain_metadata.return_value = [
        {
            "url": "dummy_url.com",
            "title": "dummy_title",
            "icon": "dummy_icon",
            "domain": "dummy_domain",
        },
        {"url": None, "title": "", "icon": "", "domain": ""},
    ]

    mock_domain_metadata_uploader.upload_favicons.side_effect = [
        ["dummy_uploaded_favicon_url", ""],
        [
            "https://test_cdn_hostname/wiki_favicon.png",
            "https://test_cdn_hostname/bloomber_favicon.png",
        ],
    ]

    mock_domain_metadata_uploader.upload_favicons.return_value = ["dummy_uploaded_favicon_url", ""]

    mocker.patch(
        "merino.jobs.navigational_suggestions.PARTNER_FAVICONS",
        [
            {
                "domain": "wikipedia",
                "url": "https://www.wikipedia.org",
                "icon": "https://test_cdn_hostname/wiki_favicon.png",
            },
            {
                "domain": "bloomberg",
                "url": "https://www.bloomberg.com",
                "icon": "https://www.bloomberg_favicon.png",
            },
        ],
    )

    construct_partner_manifest_mock = mocker.patch(
        "merino.jobs.navigational_suggestions._construct_partner_manifest",
        return_value={
            "partners": [
                {
                    "domain": "wikipedia",
                    "url": "https://www.wikipedia.org",
                    "original_icon_url": "https://test_cdn_hostname/wiki_favicon.png",
                    "gcs_icon_url": "https://test_cdn_hostname/wiki_favicon.png",
                },
                {
                    "domain": "bloomberg",
                    "url": "https://www.bloomberg.com",
                    "original_icon_url": "https://www.bloomberg_favicon.png",
                    "gcs_icon_url": "https://test_cdn_hostname/bloomberg_favicon.png",
                },
            ]
        },
    )

    prepare_domain_metadata(
        "dummy_src_project", "dummy_destination_project", "dummy_destination_blob"
    )

    expected_partner_manifest = {
        "partners": [
            {
                "domain": "wikipedia",
                "url": "https://www.wikipedia.org",
                "original_icon_url": "https://test_cdn_hostname/wiki_favicon.png",
                "gcs_icon_url": "https://test_cdn_hostname/wiki_favicon.png",
            },
            {
                "domain": "bloomberg",
                "url": "https://www.bloomberg.com",
                "original_icon_url": "https://www.bloomberg_favicon.png",
                "gcs_icon_url": "https://test_cdn_hostname/bloomberg_favicon.png",
            },
        ]
    }

    construct_partner_manifest_mock.assert_called_once()

    expected_top_picks = {
        "domains": [
            {
                "rank": 1,
                "domain": "dummy_domain",
                "categories": ["Search Engines"],
                "serp_categories": [0],
                "url": "dummy_url.com",
                "title": "dummy_title",
                "icon": "dummy_uploaded_favicon_url",
            }
        ],
        "partners": expected_partner_manifest["partners"],
    }

    mock_domain_metadata_uploader.upload_top_picks.assert_called_once_with(
        json.dumps(expected_top_picks, indent=4)
    )
