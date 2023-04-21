# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for domain_metadata_uploader.py module."""

import pytest

from merino.jobs.navigational_suggestions.domain_metadata_uploader import (
    DomainMetadataUploader,
)


@pytest.fixture
def mock_gcs_client(mocker):
    """Return a mock GCS Client instance"""
    return mocker.patch(
        "merino.jobs.navigational_suggestions.domain_metadata_uploader.Client"
    ).return_value


def test_upload_top_picks(mock_gcs_client):
    """Test if upload top picks call relevant GCS api"""
    dummy_top_picks = "dummy top picks contents"
    mock_gcs_bucket = mock_gcs_client.bucket.return_value
    mock_dst_blob = mock_gcs_bucket.blob.return_value

    domain_metadata_uploader = DomainMetadataUploader(
        "dummy_gcp_project", "dummy_gcs_bucket", None, False
    )
    domain_metadata_uploader.upload_top_picks(dummy_top_picks)

    mock_gcs_client.bucket.assert_called_once_with("dummy_gcs_bucket")
    mock_gcs_bucket.blob.assert_called_once()
    mock_dst_blob.upload_from_string.assert_called_once_with(dummy_top_picks)


def test_upload_favicons_upload_if_not_present(mock_gcs_client, mocker):
    """Test if favicons are uploaded only if not already present in GCS"""
    dummy_src_favicons = ["favicon1.png"]
    mock_gcs_bucket = mock_gcs_client.bucket.return_value
    mock_dst_blob = mock_gcs_bucket.blob.return_value

    mock_dst_blob.exists.return_value = False
    mock_dst_blob.public_url = "uploaded_favicon1.png"

    mock___download_favicon = mocker.patch(
        (
            "merino.jobs.navigational_suggestions.domain_metadata_uploader."
            "DomainMetadataUploader._download_favicon"
        )
    )
    mock___download_favicon.return_value = (bytes(255), "image/png")

    domain_metadata_uploader = DomainMetadataUploader(
        "dummy_gcp_project", "dummy_gcs_bucket", None, False
    )
    uploaded_favicons = domain_metadata_uploader.upload_favicons(dummy_src_favicons)

    mock_dst_blob.upload_from_string.assert_called_once_with(
        bytes(255), content_type="image/png"
    )
    mock_dst_blob.make_public.assert_called_once()

    assert len(uploaded_favicons) == len(dummy_src_favicons)
    assert uploaded_favicons[0] == "uploaded_favicon1.png"


def test_upload_favicons_upload_if_force_upload_set(mock_gcs_client, mocker):
    """Test if favicons are uploaded only if not already present in GCS"""
    dummy_src_favicons = ["favicon1.png"]
    mock_dst_blob = mock_gcs_client.bucket.return_value.blob.return_value

    mock_dst_blob.exists.return_value = True
    mocker.patch(
        (
            "merino.jobs.navigational_suggestions.domain_metadata_uploader."
            "DomainMetadataUploader._download_favicon"
        )
    ).return_value = (bytes(255), "image/png")

    domain_metadata_uploader = DomainMetadataUploader(
        "dummy_gcp_project", "dummy_gcs_bucket", None, True
    )
    domain_metadata_uploader.upload_favicons(dummy_src_favicons)

    mock_dst_blob.upload_from_string.assert_called_once_with(
        bytes(255), content_type="image/png"
    )
    mock_dst_blob.make_public.assert_called_once()


def test_upload_favicons_return_favicon_with_cdnhostname_when_provided(
    mock_gcs_client, mocker
):
    """Test if uploaded favicon url has cdn hostname when provided"""
    dummy_src_favicons = ["favicon1.png"]
    dummy_cdn_hostname = "dummy.cdn.hostname"
    dummy_destination_favicon_name = "dummy_destination_favicon_name"
    expected_destination_favicon_url = (
        "https://" + dummy_cdn_hostname + "/" + dummy_destination_favicon_name
    )

    mock_dst_blob = mock_gcs_client.bucket.return_value.blob.return_value
    mock_dst_blob.exists.return_value = True

    mocker.patch(
        (
            "merino.jobs.navigational_suggestions.domain_metadata_uploader."
            "DomainMetadataUploader._download_favicon"
        )
    ).return_value = (bytes(255), "image/png")

    mocker.patch(
        (
            "merino.jobs.navigational_suggestions.domain_metadata_uploader."
            "DomainMetadataUploader._destination_favicon_name"
        )
    ).return_value = dummy_destination_favicon_name

    domain_metadata_uploader = DomainMetadataUploader(
        "dummy_gcp_project", "dummy_gcs_bucket", dummy_cdn_hostname, False
    )
    uploaded_favicons = domain_metadata_uploader.upload_favicons(dummy_src_favicons)

    mock_dst_blob.public_url.assert_not_called()
    assert len(uploaded_favicons) == len(dummy_src_favicons)
    assert uploaded_favicons[0] == expected_destination_favicon_url


def test_upload_favicons_exception_returns_empty_urls(mock_gcs_client, mocker):
    """Test if an exception results into returning an empty url"""
    dummy_src_favicons = ["invalid_favicon.png"]

    domain_metadata_uploader = DomainMetadataUploader(
        "dummy_gcp_project", "dummy_gcs_bucket", None, False
    )
    uploaded_favicons = domain_metadata_uploader.upload_favicons(dummy_src_favicons)

    for uploaded_favicon in uploaded_favicons:
        assert uploaded_favicon == ""
