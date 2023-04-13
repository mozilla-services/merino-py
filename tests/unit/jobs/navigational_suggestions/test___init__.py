# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for __init__.py module."""

import json

from merino.jobs.navigational_suggestions import prepare_domain_metadata


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

    mock_domain_metadata_extractor.get_urls_and_titles.return_value = [
        {"url": "dummy_url", "title": "dummy_title"}
    ]
    mock_domain_metadata_extractor.get_second_level_domains.return_value = [
        "second_level_domain"
    ]
    mock_domain_metadata_uploader.upload_favicons.return_value = [
        "dummy_uploaded_favicon_url"
    ]

    prepare_domain_metadata(
        "dummy_src_project", "dummy_destination_project", "dummy_destination_blob"
    )

    expected_top_picks = {
        "domains": [
            {
                "rank": 1,
                "domain": "second_level_domain",
                "categories": ["Search Engines"],
                "url": "dummy_url",
                "title": "dummy_title",
                "icon": "dummy_uploaded_favicon_url",
            }
        ]
    }
    mock_domain_metadata_uploader.upload_top_picks.assert_called_once_with(
        json.dumps(expected_top_picks, indent=4)
    )
