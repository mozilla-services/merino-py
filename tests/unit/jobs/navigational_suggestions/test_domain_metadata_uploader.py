# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for domain_metadata_uploader.py module."""

import json
from logging import INFO, LogRecord
from typing import Any

import pytest
from google.cloud.storage import Blob, Bucket, Client
from pytest import LogCaptureFixture
from pytest_mock import MockerFixture

from merino.content_handler.models import BaseContentUploader, Image
from merino.jobs.navigational_suggestions.domain_metadata_uploader import (
    DomainMetadataUploader,
)
from merino.jobs.navigational_suggestions.utils import FaviconDownloader
from tests.types import FilterCaplogFixture


@pytest.fixture(name="json_domain_data")
def fixture_json_domain_data() -> str:
    """Return a JSON string of top picks data for mocking."""
    return json.dumps(
        {
            "domains": [
                {
                    "rank": 1,
                    "title": "Example",
                    "domain": "example",
                    "url": "https://example.com",
                    "icon": "",
                    "categories": ["web-browser"],
                    "similars": ["exxample", "exampple", "eexample"],
                },
                {
                    "rank": 2,
                    "title": "Firefox",
                    "domain": "firefox",
                    "url": "https://firefox.com",
                    "icon": "",
                    "categories": ["web-browser"],
                    "similars": [
                        "firefoxx",
                        "foyerfox",
                        "fiirefox",
                        "firesfox",
                        "firefoxes",
                    ],
                },
                {
                    "rank": 3,
                    "title": "Mozilla",
                    "domain": "mozilla",
                    "url": "https://mozilla.org/en-US/",
                    "icon": "",
                    "categories": ["web-browser"],
                    "similars": ["mozzilla", "mozila"],
                },
                {
                    "rank": 4,
                    "title": "Abc",
                    "domain": "abc",
                    "url": "https://abc.test",
                    "icon": "",
                    "categories": ["web-browser"],
                    "similars": ["aa", "ab", "acb", "acbc", "aecbc"],
                },
                {
                    "rank": 5,
                    "title": "BadDomain",
                    "domain": "baddomain",
                    "url": "https://baddomain.test",
                    "icon": "",
                    "categories": ["web-browser"],
                    "similars": ["bad", "badd"],
                },
                {
                    "rank": 6,
                    "title": "Subdomain Test",
                    "domain": "subdomain",
                    "url": "https://sub.subdomain.test",
                    "icon": "",
                    "categories": ["web-browser"],
                    "similars": [
                        "sub",
                    ],
                },
            ]
        }
    )


@pytest.fixture(name="json_domain_data_latest")
def fixture_json_domain_data_latest() -> str:
    """Return a JSON string of top picks data for mocking."""
    return json.dumps(
        {
            "domains": [
                {
                    "rank": 1,
                    "title": "TestExample",
                    "domain": "test-example",
                    "url": "https://testexample.com",
                    "icon": "",
                    "categories": ["web-browser"],
                    "similars": ["exxample", "exampple", "eexample"],
                },
                {
                    "rank": 2,
                    "title": "Firefox",
                    "domain": "firefox",
                    "url": "https://test.firefox.com",
                    "icon": "",
                    "categories": ["web-browser"],
                    "similars": [
                        "firefoxx",
                        "foyerfox",
                        "fiirefox",
                        "firesfox",
                        "firefoxes",
                    ],
                },
                {
                    "rank": 3,
                    "title": "Mozilla",
                    "domain": "mozilla",
                    "url": "https://mozilla.org/en-US/",
                    "icon": "",
                    "categories": ["web-browser"],
                    "similars": ["mozzilla", "mozila"],
                },
                {
                    "rank": 4,
                    "title": "Abc",
                    "domain": "abc",
                    "url": "https://abc.test",
                    "icon": "",
                    "categories": ["web-browser"],
                    "similars": ["aa", "ab", "acb", "acbc", "aecbc"],
                },
                {
                    "rank": 5,
                    "title": "BadDomain",
                    "domain": "baddomain",
                    "url": "https://baddomain.test",
                    "icon": "",
                    "categories": ["web-browser"],
                    "similars": ["bad", "badd"],
                },
                {
                    "rank": 6,
                    "title": "Subdomain Test",
                    "domain": "subdomain",
                    "url": "https://sub.subdomain.test",
                    "icon": "",
                    "categories": ["web-browser"],
                    "similars": [
                        "sub",
                    ],
                },
            ]
        }
    )


@pytest.fixture
def mock_gcs_client(mocker):
    """Return a mock GCS Client instance"""
    return mocker.patch("merino.content_handler.gcp_uploader.Client").return_value


@pytest.fixture
def mock_gcs_blob(mocker):
    """Return a mock GCS Bucket instance"""
    return mocker.patch("merino.content_handler.gcp_uploader.Blob").return_value


@pytest.fixture(name="remote_blob", autouse=True)
def fixture_remote_blob(mocker: MockerFixture, json_domain_data) -> Any:
    """Create a remote blob mock object for testing."""
    remote_blob = mocker.MagicMock(spec=Blob)
    remote_blob.name = "20220101120555_top_picks.json"
    remote_blob.download_as_text.return_value = json_domain_data
    return remote_blob


@pytest.fixture(name="remote_blob_newest", autouse=True)
def fixture_remote_blob_newest(mocker: MockerFixture, json_domain_data) -> Any:
    """Create a remote blob mock object for testing.
    Has higher timestamp, therefore newer.
    """
    remote_blob = mocker.MagicMock(spec=Blob)
    remote_blob.name = "20220501120555_top_picks.json"
    remote_blob.download_as_text.return_value = json_domain_data
    return remote_blob


@pytest.fixture(name="remote_bucket", autouse=True)
def fixture_remote_bucket(mocker: MockerFixture, remote_blob, remote_blob_newest) -> Any:
    """Create a remote bucket mock object for testing."""
    remote_bucket = mocker.MagicMock(spec=Bucket)
    remote_bucket.list_blobs.return_value = [remote_blob, remote_blob_newest]
    return remote_bucket


@pytest.fixture(name="remote_client", autouse=True)
def mock_remote_client(mocker: MockerFixture, remote_bucket):
    """Create a remote client mock object for testing"""
    remote_client = mocker.MagicMock(spec=Client)
    remote_client.get_bucket.return_value = remote_bucket
    return remote_client


@pytest.fixture
def mock_favicon_downloader(mocker) -> Any:
    """Return a mock FaviconDownloader instance"""
    favicon_downloader_mock: Any = mocker.Mock(spec=FaviconDownloader)
    favicon_downloader_mock.download_favicon.return_value = Image(
        content=bytes(255), content_type="image/png"
    )
    return favicon_downloader_mock


@pytest.fixture
def mock_gcs_uploader(mocker, remote_blob_newest) -> Any:
    """Return a mock GcsUploader instance"""
    uploader_mock: Any = mocker.Mock(spec=BaseContentUploader)
    uploader_mock.get_most_recent_file.return_value = remote_blob_newest
    return uploader_mock


def test_upload_top_picks(
    mock_gcs_uploader,
    mock_gcs_blob,
    mock_favicon_downloader,
) -> None:
    """Test if upload top picks call relevant GCS API"""
    DUMMY_TOP_PICKS = "dummy top picks contents"
    mock_blob = mock_gcs_blob

    mock_blob.name = "20220101120555_top_picks.json"

    mock_gcs_uploader.upload_content.return_value = mock_blob

    domain_metadata_uploader = DomainMetadataUploader(
        uploader=mock_gcs_uploader,
        force_upload=False,
        favicon_downloader=mock_favicon_downloader,
    )

    result = domain_metadata_uploader.upload_top_picks(DUMMY_TOP_PICKS)

    assert result == mock_blob
    assert result.name == mock_blob.name


def test_upload_favicons_upload_if_not_present(mock_favicon_downloader, mock_gcs_uploader) -> None:
    """Test that favicons are uploaded only if not already present
    in GCS when force upload is not set
    """
    FORCE_UPLOAD: bool = False
    UPLOADED_FAVICON_PUBLIC_URL = "DUMMY_PUBLIC_URL"
    dummy_favicon = Image(content=bytes(255), content_type="image/png")

    mock_gcs_uploader.upload_image.return_value = UPLOADED_FAVICON_PUBLIC_URL

    domain_metadata_uploader = DomainMetadataUploader(
        uploader=mock_gcs_uploader,
        force_upload=FORCE_UPLOAD,
        favicon_downloader=mock_favicon_downloader,
    )

    uploaded_favicons = domain_metadata_uploader.upload_favicons(["favicon1.png"])
    destination_favicon_name = domain_metadata_uploader.destination_favicon_name(dummy_favicon)

    assert uploaded_favicons == [UPLOADED_FAVICON_PUBLIC_URL]
    mock_gcs_uploader.upload_image.assert_called_once_with(
        dummy_favicon, destination_favicon_name, forced_upload=FORCE_UPLOAD
    )


def test_upload_favicons_upload_if_force_upload_set(
    mock_favicon_downloader, mock_gcs_uploader
) -> None:
    """Test that favicons are uploaded always when force upload is set"""
    FORCE_UPLOAD: bool = True
    UPLOADED_FAVICON_PUBLIC_URL = "DUMMY_PUBLIC_URL"
    dummy_favicon = Image(content=bytes(255), content_type="image/png")

    mock_gcs_uploader.upload_image.return_value = UPLOADED_FAVICON_PUBLIC_URL

    domain_metadata_uploader = DomainMetadataUploader(
        uploader=mock_gcs_uploader,
        force_upload=FORCE_UPLOAD,
        favicon_downloader=mock_favicon_downloader,
    )

    uploaded_favicons = domain_metadata_uploader.upload_favicons(["favicon1.png"])
    destination_favicon_name = domain_metadata_uploader.destination_favicon_name(dummy_favicon)

    assert uploaded_favicons == [UPLOADED_FAVICON_PUBLIC_URL]
    mock_gcs_uploader.upload_image.assert_called_once_with(
        dummy_favicon, destination_favicon_name, forced_upload=FORCE_UPLOAD
    )


def test_upload_favicons_return_favicon_with_cdn_hostname_when_provided(
    mock_gcs_client, mock_favicon_downloader, mock_gcs_uploader
) -> None:
    """Test if uploaded favicon url has cdn hostname when provided"""
    CDN_HOSTNAME = "dummy.cdn.hostname"

    mock_gcs_uploader.upload_image.return_value = CDN_HOSTNAME
    mock_dst_blob = mock_gcs_client.bucket.return_value.blob.return_value
    mock_dst_blob.exists.return_value = True

    domain_metadata_uploader = DomainMetadataUploader(
        uploader=mock_gcs_uploader,
        force_upload=False,
        favicon_downloader=mock_favicon_downloader,
    )
    uploaded_favicons = domain_metadata_uploader.upload_favicons(["favicon1.png"])

    mock_dst_blob.public_url.assert_not_called()
    for uploaded_favicon in uploaded_favicons:
        assert "dummy.cdn.hostname" in uploaded_favicon


def test_upload_favicons_return_empty_url_for_failed_favicon_download(
    mock_gcs_client, mock_favicon_downloader, mock_gcs_uploader
) -> None:
    """Test if a failure in downloading favicon from the scraped url returns an empty uploaded
    favicon url
    """
    mock_favicon_downloader.download_favicon.return_value = None

    domain_metadata_uploader = DomainMetadataUploader(
        uploader=mock_gcs_uploader,
        force_upload=False,
        favicon_downloader=mock_favicon_downloader,
    )
    uploaded_favicons = domain_metadata_uploader.upload_favicons(["favicon1.png"])

    for uploaded_favicon in uploaded_favicons:
        assert uploaded_favicon == ""


def test_get_latest_file_for_diff(
    mock_favicon_downloader,
    mock_gcs_uploader,
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
    remote_blob_newest,
) -> None:
    """Test acquiring the latest file data from mock GCS bucket.
    Also checks case if there is no data
    """
    caplog.set_level(INFO)
    default_domain_metadata_uploader = DomainMetadataUploader(
        uploader=mock_gcs_uploader,
        force_upload=False,
        favicon_downloader=mock_favicon_downloader,
    )

    result = default_domain_metadata_uploader.get_latest_file_for_diff()
    records: list[LogRecord] = filter_caplog(
        caplog.records, "merino.jobs.navigational_suggestions.domain_metadata_uploader"
    )
    assert isinstance(result, dict)
    assert result["domains"]
    assert len(result["domains"]) == 6

    assert len(records) == 1
    assert records[0].message.startswith(f"Domain file {remote_blob_newest.name} acquired.")


def test_get_latest_file_for_diff_when_no_file_is_returned_by_the_uploader(
    mock_favicon_downloader,
    mock_gcs_uploader,
) -> None:
    """Test the case where the uploader returns no most recent file"""
    mock_gcs_uploader.get_most_recent_file.return_value = None

    default_domain_metadata_uploader = DomainMetadataUploader(
        uploader=mock_gcs_uploader,
        force_upload=False,
        favicon_downloader=mock_favicon_downloader,
    )

    result = default_domain_metadata_uploader.get_latest_file_for_diff()

    assert result is None
