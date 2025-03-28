# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for navigational_suggestions __init__.py module."""

from unittest.mock import MagicMock, patch

import pytest

from merino.jobs.navigational_suggestions import (
    _construct_partner_manifest,
    _construct_top_picks,
    _write_xcom_file,
    prepare_domain_metadata,
)


def test_construct_top_picks_source_field():
    """Test that _construct_top_picks includes the source field in the output JSON data."""
    # Mock input data
    domain_data = [
        {"rank": 1, "categories": ["web"], "source": "top-picks"},
        {"rank": 2, "categories": ["shopping"], "source": "custom-domains"},
    ]

    domain_metadata = [
        {
            "domain": "example.com",
            "url": "https://example.com",
            "title": "Example",
            "icon": "icon1",
        },
        {"domain": "amazon.ca", "url": "https://amazon.ca", "title": "Amazon", "icon": "icon2"},
    ]

    result = _construct_top_picks(domain_data, domain_metadata)

    # Check if source field is included correctly in the results
    assert "domains" in result
    assert len(result["domains"]) == 2
    assert result["domains"][0]["source"] == "top-picks"
    assert result["domains"][1]["source"] == "custom-domains"

    # Check other fields
    assert result["domains"][0]["domain"] == "example.com"
    assert result["domains"][0]["url"] == "https://example.com"
    assert result["domains"][0]["title"] == "Example"
    assert result["domains"][0]["icon"] == "icon1"

    assert result["domains"][1]["domain"] == "amazon.ca"
    assert result["domains"][1]["url"] == "https://amazon.ca"
    assert result["domains"][1]["title"] == "Amazon"
    assert result["domains"][1]["icon"] == "icon2"


def test_construct_top_picks_missing_source_field():
    """Test that _construct_top_picks handles missing source field correctly."""
    # Mock input data with missing source field
    domain_data = [
        {"rank": 1, "categories": ["web"]},  # No source field
    ]

    domain_metadata = [
        {
            "domain": "example.com",
            "url": "https://example.com",
            "title": "Example",
            "icon": "icon1",
        },
    ]

    result = _construct_top_picks(domain_data, domain_metadata)

    # Check if source field defaults to "top-picks"
    assert "domains" in result
    assert len(result["domains"]) == 1
    assert result["domains"][0]["source"] == "top-picks"


def test_construct_partner_manifest():
    """Test the _construct_partner_manifest function."""
    partner_favicon_source = [
        {
            "domain": "partner1.com",
            "url": "https://partner1.com",
            "icon": "https://partner1.com/favicon.ico",
        },
        {
            "domain": "partner2.com",
            "url": "https://partner2.com",
            "icon": "https://partner2.com/favicon.ico",
        },
    ]

    uploaded_favicons = [
        "https://cdn.example.com/partner1-favicon.ico",
        "https://cdn.example.com/partner2-favicon.ico",
    ]

    result = _construct_partner_manifest(partner_favicon_source, uploaded_favicons)

    assert "partners" in result
    assert len(result["partners"]) == 2

    assert result["partners"][0]["domain"] == "partner1.com"
    assert result["partners"][0]["url"] == "https://partner1.com"
    assert result["partners"][0]["original_icon_url"] == "https://partner1.com/favicon.ico"
    assert result["partners"][0]["gcs_icon_url"] == "https://cdn.example.com/partner1-favicon.ico"

    assert result["partners"][1]["domain"] == "partner2.com"
    assert result["partners"][1]["url"] == "https://partner2.com"
    assert result["partners"][1]["original_icon_url"] == "https://partner2.com/favicon.ico"
    assert result["partners"][1]["gcs_icon_url"] == "https://cdn.example.com/partner2-favicon.ico"


def test_construct_partner_manifest_length_mismatch():
    """Test _construct_partner_manifest with mismatched input lengths."""
    partner_favicon_source = [
        {
            "domain": "partner1.com",
            "url": "https://partner1.com",
            "icon": "https://partner1.com/favicon.ico",
        },
        {
            "domain": "partner2.com",
            "url": "https://partner2.com",
            "icon": "https://partner2.com/favicon.ico",
        },
    ]

    uploaded_favicons = [
        "https://cdn.example.com/partner1-favicon.ico",
        # Missing second favicon URL
    ]

    with pytest.raises(
        ValueError, match="Mismatch: The number of favicons and GCS URLs must be the same."
    ):
        _construct_partner_manifest(partner_favicon_source, uploaded_favicons)


def test_write_xcom_file():
    """Test _write_xcom_file function."""
    test_data = {"key": "value", "numbers": [1, 2, 3]}

    # Create a mock file object instead of using a real temporary file
    mock_file = MagicMock()

    with patch("builtins.open", return_value=mock_file):
        _write_xcom_file(test_data)

        # Verify that json.dump was called with our test data to the file
        mock_file.__enter__.return_value.write.assert_called()
        # We can verify that open was called with the right path
        open.assert_called_once_with("/airflow/xcom/return.json", "w")


@patch("merino.jobs.navigational_suggestions.DomainDataDownloader")
@patch("merino.jobs.navigational_suggestions.DomainMetadataUploader")
@patch("merino.jobs.navigational_suggestions.DomainMetadataExtractor")
@patch("merino.jobs.navigational_suggestions.GcsUploader")
@patch("merino.jobs.navigational_suggestions.AsyncFaviconDownloader")
@patch("merino.jobs.navigational_suggestions.DomainDiff")
@patch(
    "merino.jobs.navigational_suggestions.PARTNER_FAVICONS",
    [
        {
            "domain": "partner.com",
            "url": "https://partner.com",
            "icon": "https://partner.com/favicon.ico",
        }
    ],
)
def test_prepare_domain_metadata(
    mock_domain_diff_class,
    mock_favicon_downloader,
    mock_gcs_uploader,
    mock_extractor_class,
    mock_uploader_class,
    mock_downloader_class,
):
    """Test prepare_domain_metadata function."""
    # Setup mocks
    mock_downloader = MagicMock()
    mock_downloader_class.return_value = mock_downloader
    mock_downloader.download_data.return_value = [
        {"rank": 1, "categories": ["web"], "source": "top-picks"}
    ]

    mock_uploader = MagicMock()
    mock_uploader_class.return_value = mock_uploader
    mock_uploader.get_latest_file_for_diff.return_value = None
    mock_uploader.upload_favicons.return_value = ["https://cdn.example.com/partner-favicon.ico"]

    mock_blob = MagicMock()
    mock_blob.name = "top_picks.json"
    mock_blob.public_url = "https://cdn.example.com/top_picks.json"
    mock_uploader.upload_top_picks.return_value = mock_blob

    mock_extractor = MagicMock()
    mock_extractor_class.return_value = mock_extractor
    mock_extractor.process_domain_metadata.return_value = [
        {
            "domain": "example.com",
            "url": "https://example.com",
            "title": "Example",
            "icon": "https://cdn.example.com/favicon.ico",
        }
    ]

    mock_domain_diff = MagicMock()
    mock_domain_diff_class.return_value = mock_domain_diff
    mock_domain_diff.compare_top_picks.return_value = (10, 5, 3)
    mock_domain_diff.create_diff.return_value = {"unchanged": 10, "added": 5, "url_changes": 3}

    # Call the function
    with patch("merino.jobs.navigational_suggestions._write_xcom_file") as mock_write_xcom:
        prepare_domain_metadata(
            source_gcp_project="source-project",
            destination_gcp_project="dest-project",
            destination_gcs_bucket="dest-bucket",
            destination_cdn_hostname="cdn.example.com",
            force_upload=True,
            write_xcom=True,
            min_favicon_width=48,
        )

    # Verify calls
    mock_downloader_class.assert_called_once_with("source-project")
    mock_downloader.download_data.assert_called_once()

    mock_gcs_uploader.assert_called_once_with("dest-project", "dest-bucket", "cdn.example.com")

    mock_extractor_class.assert_called_once()
    mock_extractor.process_domain_metadata.assert_called_once_with(
        [{"rank": 1, "categories": ["web"], "source": "top-picks"}], 48, uploader=mock_uploader
    )

    mock_uploader.upload_favicons.assert_called_once_with(["https://partner.com/favicon.ico"])

    mock_uploader.get_latest_file_for_diff.assert_called_once()

    mock_domain_diff_class.assert_called_once()
    mock_domain_diff.compare_top_picks.assert_called_once()
    mock_domain_diff.create_diff.assert_called_once_with(
        file_name="top_picks.json", unchanged=10, domains=5, urls=3
    )

    mock_write_xcom.assert_called_once_with(
        {
            "top_pick_url": "https://cdn.example.com/top_picks.json",
            "diff": {"unchanged": 10, "added": 5, "url_changes": 3},
        }
    )


@patch("merino.jobs.navigational_suggestions.DomainDataDownloader")
@patch("merino.jobs.navigational_suggestions.DomainMetadataUploader")
@patch("merino.jobs.navigational_suggestions.DomainMetadataExtractor")
@patch("merino.jobs.navigational_suggestions.GcsUploader")
@patch("merino.jobs.navigational_suggestions.AsyncFaviconDownloader")
@patch("merino.jobs.navigational_suggestions.DomainDiff")
@patch(
    "merino.jobs.navigational_suggestions.PARTNER_FAVICONS",
    [
        {
            "domain": "partner.com",
            "url": "https://partner.com",
            "icon": "https://partner.com/favicon.ico",
        }
    ],
)
def test_prepare_domain_metadata_with_existing_file(
    mock_domain_diff_class,
    mock_favicon_downloader,
    mock_gcs_uploader,
    mock_extractor_class,
    mock_uploader_class,
    mock_downloader_class,
):
    """Test prepare_domain_metadata function with an existing top picks file."""
    # Setup mocks
    mock_downloader = MagicMock()
    mock_downloader_class.return_value = mock_downloader
    mock_downloader.download_data.return_value = [
        {"rank": 1, "categories": ["web"], "source": "top-picks"}
    ]

    mock_uploader = MagicMock()
    mock_uploader_class.return_value = mock_uploader

    # Return existing data for diff
    mock_uploader.get_latest_file_for_diff.return_value = {
        "domains": [
            {
                "rank": 1,
                "domain": "example.com",
                "url": "https://example.com",
                "title": "Example",
                "icon": "old-icon-url",
                "categories": ["web"],
                "source": "top-picks",
            }
        ]
    }

    mock_uploader.upload_favicons.return_value = ["https://cdn.example.com/partner-favicon.ico"]

    mock_blob = MagicMock()
    mock_blob.name = "top_picks.json"
    mock_blob.public_url = "https://cdn.example.com/top_picks.json"
    mock_uploader.upload_top_picks.return_value = mock_blob

    mock_extractor = MagicMock()
    mock_extractor_class.return_value = mock_extractor
    mock_extractor.process_domain_metadata.return_value = [
        {
            "domain": "example.com",
            "url": "https://example.com",
            "title": "Example",
            "icon": "https://cdn.example.com/favicon.ico",
        }
    ]

    mock_domain_diff = MagicMock()
    mock_domain_diff_class.return_value = mock_domain_diff
    mock_domain_diff.compare_top_picks.return_value = (10, 5, 3)
    mock_domain_diff.create_diff.return_value = {"unchanged": 10, "added": 5, "url_changes": 3}

    # Call the function without write_xcom
    prepare_domain_metadata(
        source_gcp_project="source-project",
        destination_gcp_project="dest-project",
        destination_gcs_bucket="dest-bucket",
        destination_cdn_hostname="cdn.example.com",
        force_upload=True,
        write_xcom=False,  # No XCom writing in this test
        min_favicon_width=48,
    )

    # Verify the domain diff was created with the correct data
    mock_domain_diff_class.assert_called_once()
    # Confirm compare_top_picks was called with both old and new data
    mock_domain_diff.compare_top_picks.assert_called_once()
