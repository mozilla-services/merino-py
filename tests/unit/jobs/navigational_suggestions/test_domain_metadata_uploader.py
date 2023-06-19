# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for domain_metadata_uploader.py module."""
from typing import Any

import pytest

from merino.jobs.navigational_suggestions.domain_metadata_uploader import (
    DomainMetadataUploader,
)
from merino.jobs.navigational_suggestions.utils import FaviconDownloader, FaviconImage


@pytest.fixture
def mock_gcs_client(mocker):
    """Return a mock GCS Client instance"""
    return mocker.patch(
        "merino.jobs.navigational_suggestions.domain_metadata_uploader.Client"
    ).return_value


@pytest.fixture
def mock_favicon_downloader(mocker):
    """Return a mock FaviconDownloader instance"""
    favicon_downloader_mock: Any = mocker.Mock(spec=FaviconDownloader)
    favicon_downloader_mock.download_favicon.return_value = FaviconImage(
        content=bytes(255), content_type="image/png"
    )
    return favicon_downloader_mock


def test_upload_top_picks(mock_gcs_client, mock_favicon_downloader):
    """Test if upload top picks call relevant GCS api"""
    DUMMY_TOP_PICKS = "dummy top picks contents"
    mock_gcs_bucket = mock_gcs_client.bucket.return_value
    mock_dst_blob = mock_gcs_bucket.blob.return_value

    domain_metadata_uploader = DomainMetadataUploader(
        "dummy_gcp_project", "dummy_gcs_bucket", None, False, mock_favicon_downloader
    )
    domain_metadata_uploader.upload_top_picks(DUMMY_TOP_PICKS)

    mock_gcs_client.bucket.assert_called_once_with("dummy_gcs_bucket")
    mock_gcs_bucket.blob.assert_called_once()
    mock_dst_blob.upload_from_string.assert_called_once_with(DUMMY_TOP_PICKS)


def test_upload_favicons_upload_if_not_present(
    mock_gcs_client, mock_favicon_downloader
):
    """Test that favicons are uploaded only if not already present in GCS when
    force upload is not set
    """
    FORCE_UPLOAD: bool = False
    UPLOADED_FAVICON_PUBLIC_URL = "DUMMY_PUBLIC_URL"

    mock_dst_blob = mock_gcs_client.bucket.return_value.blob.return_value
    mock_dst_blob.exists.return_value = False
    mock_dst_blob.public_url = UPLOADED_FAVICON_PUBLIC_URL

    domain_metadata_uploader = DomainMetadataUploader(
        "dummy_gcp_project",
        "dummy_gcs_bucket",
        None,
        FORCE_UPLOAD,
        mock_favicon_downloader,
    )
    uploaded_favicons = domain_metadata_uploader.upload_favicons(["favicon1.png"])

    mock_dst_blob.upload_from_string.assert_called_once_with(
        bytes(255), content_type="image/png"
    )
    mock_dst_blob.make_public.assert_called_once()
    assert uploaded_favicons == [UPLOADED_FAVICON_PUBLIC_URL]


def test_upload_favicons_upload_if_force_upload_set(
    mock_gcs_client, mock_favicon_downloader
):
    """Test that favicons are uploaded always when force upload is set"""
    FORCE_UPLOAD: bool = True
    mock_dst_blob = mock_gcs_client.bucket.return_value.blob.return_value
    mock_dst_blob.exists.return_value = True

    domain_metadata_uploader = DomainMetadataUploader(
        "dummy_gcp_project",
        "dummy_gcs_bucket",
        None,
        FORCE_UPLOAD,
        mock_favicon_downloader,
    )
    domain_metadata_uploader.upload_favicons(["favicon1.png"])

    mock_dst_blob.upload_from_string.assert_called_once_with(
        bytes(255), content_type="image/png"
    )
    mock_dst_blob.make_public.assert_called_once()


def test_upload_favicons_return_favicon_with_cdnhostname_when_provided(
    mock_gcs_client, mock_favicon_downloader
):
    """Test if uploaded favicon url has cdn hostname when provided"""
    CDN_HOSTNAME = "dummy.cdn.hostname"

    mock_dst_blob = mock_gcs_client.bucket.return_value.blob.return_value
    mock_dst_blob.exists.return_value = True

    domain_metadata_uploader = DomainMetadataUploader(
        "dummy_gcp_project",
        "dummy_gcs_bucket",
        CDN_HOSTNAME,
        False,
        mock_favicon_downloader,
    )
    uploaded_favicons = domain_metadata_uploader.upload_favicons(["favicon1.png"])

    mock_dst_blob.public_url.assert_not_called()
    for uploaded_favicon in uploaded_favicons:
        assert CDN_HOSTNAME in uploaded_favicon


def test_upload_favicons_return_empty_url_for_failed_favicon_download(
    mock_gcs_client, mock_favicon_downloader
):
    """Test if a failure in downloading favicon from the scraped url returns an empty
    uploaded favicon url
    """
    mock_favicon_downloader.download_favicon.return_value = None

    domain_metadata_uploader = DomainMetadataUploader(
        "dummy_gcp_project", "dummy_gcs_bucket", None, False, mock_favicon_downloader
    )
    uploaded_favicons = domain_metadata_uploader.upload_favicons(["favicon1.png"])

    for uploaded_favicon in uploaded_favicons:
        assert uploaded_favicon == ""
