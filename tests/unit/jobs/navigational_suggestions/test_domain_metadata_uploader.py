# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for domain_metadata_uploader.py module."""
import datetime
import json
from logging import INFO, LogRecord
from typing import Any

import pytest
from freezegun import freeze_time
from google.cloud.storage import Blob, Bucket, Client
from pytest import LogCaptureFixture
from pytest_mock import MockerFixture

from merino.jobs.navigational_suggestions.domain_metadata_uploader import (
    DomainMetadataUploader,
)
from merino.jobs.navigational_suggestions.utils import FaviconDownloader, FaviconImage
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
    return mocker.patch(
        "merino.jobs.navigational_suggestions.domain_metadata_uploader.Client"
    ).return_value


@pytest.fixture
def mock_gcs_bucket(mocker):
    """Return a mock GCS Bucket instance"""
    bucket = mocker.patch(
        "merino.jobs.navigational_suggestions.domain_metadata_uploader.Bucket"
    ).return_value
    bucket.name = "mock-bucket"
    return bucket


@pytest.fixture
def mock_gcs_blob(mocker):
    """Return a mock GCS Bucket instance"""
    return mocker.patch(
        "merino.jobs.navigational_suggestions.domain_metadata_uploader.Blob"
    ).return_value


@pytest.fixture(name="remote_blob", autouse=True)
def fixture_remote_blob(mocker: MockerFixture, json_domain_data) -> Any:
    """Create a remote blob mock object for testing."""
    remote_blob = mocker.MagicMock(spec=Blob)
    remote_blob.name = "1681866452_top_picks_latest.json"
    remote_blob.download_as_text.return_value = json_domain_data
    return remote_blob


@pytest.fixture(name="remote_bucket", autouse=True)
def fixture_remote_bucket(mocker: MockerFixture, remote_blob) -> Any:
    """Create a remote bucket mock object for testing."""
    remote_bucket = mocker.MagicMock(spec=Bucket)
    remote_bucket.list_blobs.return_value = [remote_blob]
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
    favicon_downloader_mock.download_favicon.return_value = FaviconImage(
        content=bytes(255), content_type="image/png"
    )
    return favicon_downloader_mock


@freeze_time("2022-01-01 00:00:00")
def test_destination_top_pick_name() -> None:
    """Test the file name generation creates the expected file name for the blob."""
    current = datetime.datetime.now()
    suffix = DomainMetadataUploader.DESTINATION_TOP_PICK_FILE_NAME_SUFFIX
    result = DomainMetadataUploader._destination_top_pick_name(suffix=suffix)
    expected_result = f"{str(int(current.timestamp()))}_{suffix}"

    assert result == expected_result


def test_remove_latest_from_all_top_picks_files(
    mocker, mock_gcs_client, mock_gcs_bucket, mock_gcs_blob, mock_favicon_downloader
) -> None:
    """Test that updating the `_latest` suffix successfully alters the file name."""
    domain_metadata_uploader = DomainMetadataUploader(
        destination_gcp_project="dummy_gcp_project",
        destination_bucket_name="dummy_gcs_bucket",
        destination_cdn_hostname="",
        force_upload=False,
        favicon_downloader=mock_favicon_downloader,
    )

    file_suffix = DomainMetadataUploader.DESTINATION_TOP_PICK_FILE_NAME_SUFFIX
    mock_gcs_blob.name = "0_top_picks_latest.json"
    mock_gcs_client.list_blobs.return_value = [mock_gcs_blob]
    mocker.patch.object(mock_gcs_bucket, "copy_blob")
    mocker.patch.object(mock_gcs_bucket, "delete_blob")

    domain_metadata_uploader.remove_latest_from_all_top_picks_files(
        bucket_name=mock_gcs_bucket.name,
        file_suffix=file_suffix,
        bucket=mock_gcs_bucket,
        storage_client=mock_gcs_client,
    )

    mock_gcs_client.list_blobs.assert_called_once()
    mock_gcs_bucket.copy_blob.assert_called_once()
    mock_gcs_bucket.delete_blob.assert_called_once()


def test_upload_top_picks(mock_gcs_client, mock_favicon_downloader) -> None:
    """Test if upload top picks call relevant GCS api"""
    DUMMY_TOP_PICKS = "dummy top picks contents"
    mock_gcs_bucket = mock_gcs_client.bucket.return_value
    mock_dst_blob = mock_gcs_bucket.blob.return_value

    domain_metadata_uploader = DomainMetadataUploader(
        destination_gcp_project="dummy_gcp_project",
        destination_bucket_name="dummy_gcs_bucket",
        destination_cdn_hostname="",
        force_upload=False,
        favicon_downloader=mock_favicon_downloader,
    )
    domain_metadata_uploader.upload_top_picks(DUMMY_TOP_PICKS)

    mock_gcs_client.bucket.assert_called_once_with("dummy_gcs_bucket")
    mock_gcs_bucket.blob.assert_called_once()
    mock_dst_blob.upload_from_string.assert_called_once_with(DUMMY_TOP_PICKS)


def test_upload_favicons_upload_if_not_present(
    mock_gcs_client, mock_favicon_downloader
) -> None:
    """Test that favicons are uploaded only if not already present in GCS when
    force upload is not set
    """
    FORCE_UPLOAD: bool = False
    UPLOADED_FAVICON_PUBLIC_URL = "DUMMY_PUBLIC_URL"

    mock_dst_blob = mock_gcs_client.bucket.return_value.blob.return_value
    mock_dst_blob.exists.return_value = False
    mock_dst_blob.public_url = UPLOADED_FAVICON_PUBLIC_URL

    domain_metadata_uploader = DomainMetadataUploader(
        destination_gcp_project="dummy_gcp_project",
        destination_bucket_name="dummy_gcs_bucket",
        destination_cdn_hostname="",
        force_upload=FORCE_UPLOAD,
        favicon_downloader=mock_favicon_downloader,
    )
    uploaded_favicons = domain_metadata_uploader.upload_favicons(["favicon1.png"])

    mock_dst_blob.upload_from_string.assert_called_once_with(
        bytes(255), content_type="image/png"
    )
    mock_dst_blob.make_public.assert_called_once()
    assert uploaded_favicons == [UPLOADED_FAVICON_PUBLIC_URL]


def test_upload_favicons_upload_if_force_upload_set(
    mock_gcs_client, mock_favicon_downloader
) -> None:
    """Test that favicons are uploaded always when force upload is set"""
    FORCE_UPLOAD: bool = True
    mock_dst_blob = mock_gcs_client.bucket.return_value.blob.return_value
    mock_dst_blob.exists.return_value = True

    domain_metadata_uploader = DomainMetadataUploader(
        destination_gcp_project="dummy_gcp_project",
        destination_bucket_name="dummy_gcs_bucket",
        destination_cdn_hostname="",
        force_upload=FORCE_UPLOAD,
        favicon_downloader=mock_favicon_downloader,
    )
    domain_metadata_uploader.upload_favicons(["favicon1.png"])

    mock_dst_blob.upload_from_string.assert_called_once_with(
        bytes(255), content_type="image/png"
    )
    mock_dst_blob.make_public.assert_called_once()


def test_upload_favicons_return_favicon_with_cdnhostname_when_provided(
    mock_gcs_client, mock_favicon_downloader
) -> None:
    """Test if uploaded favicon url has cdn hostname when provided"""
    CDN_HOSTNAME = "dummy.cdn.hostname"

    mock_dst_blob = mock_gcs_client.bucket.return_value.blob.return_value
    mock_dst_blob.exists.return_value = True

    domain_metadata_uploader = DomainMetadataUploader(
        destination_gcp_project="dummy_gcp_project",
        destination_bucket_name="dummy_gcs_bucket",
        destination_cdn_hostname=CDN_HOSTNAME,
        force_upload=False,
        favicon_downloader=mock_favicon_downloader,
    )
    uploaded_favicons = domain_metadata_uploader.upload_favicons(["favicon1.png"])

    mock_dst_blob.public_url.assert_not_called()
    for uploaded_favicon in uploaded_favicons:
        assert CDN_HOSTNAME in uploaded_favicon


def test_upload_favicons_return_empty_url_for_failed_favicon_download(
    mock_gcs_client, mock_favicon_downloader
) -> None:
    """Test if a failure in downloading favicon from the scraped url returns an empty
    uploaded favicon url
    """
    mock_favicon_downloader.download_favicon.return_value = None

    domain_metadata_uploader = DomainMetadataUploader(
        destination_gcp_project="dummy_gcp_project",
        destination_bucket_name="dummy_gcs_bucket",
        destination_cdn_hostname="",
        force_upload=False,
        favicon_downloader=mock_favicon_downloader,
    )
    uploaded_favicons = domain_metadata_uploader.upload_favicons(["favicon1.png"])

    for uploaded_favicon in uploaded_favicons:
        assert uploaded_favicon == ""


def test_get_latest_file_for_diff(
    mock_favicon_downloader,
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
    remote_blob,
    remote_client,
    mocker,
) -> None:
    """Test acquiring the latest file data from mock GCS bucket.
    Also checks case if there is no data.
    """
    mocker.patch(
        "merino.jobs.navigational_suggestions.domain_metadata_uploader.Client"
    ).return_value = remote_client
    caplog.set_level(INFO)
    default_domain_metadata_uploader = DomainMetadataUploader(
        destination_gcp_project="dummy_gcp_project",
        destination_bucket_name="dummy_gcs_bucket",
        destination_cdn_hostname="",
        force_upload=False,
        favicon_downloader=mock_favicon_downloader,
    )

    result = default_domain_metadata_uploader.get_latest_file_for_diff(
        client=remote_client
    )
    records: list[LogRecord] = filter_caplog(
        caplog.records, "merino.jobs.navigational_suggestions.domain_metadata_uploader"
    )
    assert isinstance(result, dict)
    assert result["domains"]
    assert len(result["domains"]) == 6

    assert len(records) == 1
    assert records[0].message.startswith(f"Domain file {remote_blob.name} acquired.")


def test_process_domains(
    mock_gcs_blob,
    mock_gcs_client,
    mock_favicon_downloader,
    json_domain_data,
) -> None:
    """Test that the domain list can be processed and a list of all
    second-level domains are returned.
    """
    default_domain_metadata_uploader = DomainMetadataUploader(
        destination_gcp_project="dummy_gcp_project",
        destination_bucket_name="dummy_gcs_bucket",
        destination_cdn_hostname="",
        force_upload=False,
        favicon_downloader=mock_favicon_downloader,
    )
    mock_gcs_blob.name = "0_top_picks_latest.json"
    mock_gcs_client.list_blobs.return_value = [mock_gcs_blob]
    expected_domains = [
        "example",
        "firefox",
        "mozilla",
        "abc",
        "baddomain",
        "subdomain",
    ]
    processed_domains = default_domain_metadata_uploader.process_domains(
        domain_data=json.loads(json_domain_data)
    )
    assert processed_domains == expected_domains


def test_process_urls(
    mock_gcs_blob, mock_gcs_client, json_domain_data, mock_favicon_downloader
) -> None:
    """Test that the domain list can be processed and a list of all
    urls are returned.
    """
    default_domain_metadata_uploader = DomainMetadataUploader(
        destination_gcp_project="dummy_gcp_project",
        destination_bucket_name="dummy_gcs_bucket",
        destination_cdn_hostname="",
        force_upload=False,
        favicon_downloader=mock_favicon_downloader,
    )
    mock_gcs_blob.name = "0_top_picks_latest.json"
    mock_gcs_client.list_blobs.return_value = [mock_gcs_blob]
    expected_urls = [
        "https://example.com",
        "https://firefox.com",
        "https://mozilla.org/en-US/",
        "https://abc.test",
        "https://baddomain.test",
        "https://sub.subdomain.test",
    ]
    processed_urls = default_domain_metadata_uploader.process_urls(
        domain_data=json.loads(json_domain_data)
    )
    assert processed_urls == expected_urls


def test_process_categories(
    mock_gcs_blob, mock_gcs_client, mock_favicon_downloader, json_domain_data
) -> None:
    """Test that the domain list can be processed and a list of all
    distinct categories.
    """
    default_domain_metadata_uploader = DomainMetadataUploader(
        destination_gcp_project="dummy_gcp_project",
        destination_bucket_name="dummy_gcs_bucket",
        destination_cdn_hostname="",
        force_upload=False,
        favicon_downloader=mock_favicon_downloader,
    )
    mock_gcs_blob.name = "0_top_picks_latest.json"
    mock_gcs_client.list_blobs.return_value = [mock_gcs_blob]
    expected_categories = ["web-browser"]
    processed_categories = default_domain_metadata_uploader.process_categories(
        domain_data=json.loads(json_domain_data)
    )
    assert processed_categories == expected_categories


def test_check_url_for_subdomain(
    mock_gcs_blob, mock_gcs_client, mock_favicon_downloader, json_domain_data
) -> None:
    """Test that the domain list can be processed and a list of all
    distinct categories.
    """
    default_domain_metadata_uploader = DomainMetadataUploader(
        destination_gcp_project="dummy_gcp_project",
        destination_bucket_name="dummy_gcs_bucket",
        destination_cdn_hostname="",
        force_upload=False,
        favicon_downloader=mock_favicon_downloader,
    )
    mock_gcs_blob.name = "0_top_picks_latest.json"
    mock_gcs_client.list_blobs.return_value = [mock_gcs_blob]
    expected_subdomains = [
        {"rank": 6, "domain": "subdomain", "url": "https://sub.subdomain.test"}
    ]
    subdomain_occurences = default_domain_metadata_uploader.check_url_for_subdomain(
        domain_data=json.loads(json_domain_data)
    )

    assert subdomain_occurences == expected_subdomains


def test_compare_top_picks(
    mock_favicon_downloader,
    json_domain_data_latest,
    remote_client,
    mocker,
) -> None:
    """Test comparision of latest and previous Top Picks data."""
    mocker.patch(
        "merino.jobs.navigational_suggestions.domain_metadata_uploader.Client"
    ).return_value = remote_client
    default_domain_metadata_uploader = DomainMetadataUploader(
        destination_gcp_project="dummy_gcp_project",
        destination_bucket_name="dummy_gcs_bucket",
        destination_cdn_hostname="",
        force_upload=False,
        favicon_downloader=mock_favicon_downloader,
    )
    latest_result = default_domain_metadata_uploader.get_latest_file_for_diff(
        client=remote_client
    )
    mocker.patch.object(
        default_domain_metadata_uploader, "get_latest_file_for_diff"
    ).return_value = latest_result

    result = default_domain_metadata_uploader.compare_top_picks(
        new_top_picks=json_domain_data_latest
    )
    expected_categories = ["web-browser"]
    expected_unchanged = {"subdomain", "firefox", "baddomain", "abc", "mozilla"}
    expected_added_domains = {"test-example"}
    expected_added_urls = {"https://testexample.com", "https://test.firefox.com"}
    expected_subdomains = [
        {"rank": 1, "domain": "test-example", "url": "https://testexample.com"},
        {"rank": 2, "domain": "firefox", "url": "https://test.firefox.com"},
        {"rank": 6, "domain": "subdomain", "url": "https://sub.subdomain.test"},
    ]
    assert result[0] == expected_categories
    assert result[1] == expected_unchanged
    assert result[2] == expected_added_domains
    assert result[3] == expected_added_urls
    assert result[4] == expected_subdomains


def test_create_diff_file(
    mock_favicon_downloader,
    json_domain_data_latest,
    remote_client,
    remote_blob,
    mocker,
) -> None:
    """Test that the expected diff file is generated."""
    mocker.patch(
        "merino.jobs.navigational_suggestions.domain_metadata_uploader.Client"
    ).return_value = remote_client
    default_domain_metadata_uploader = DomainMetadataUploader(
        destination_gcp_project="dummy_gcp_project",
        destination_bucket_name="dummy_gcs_bucket",
        destination_cdn_hostname="",
        force_upload=False,
        favicon_downloader=mock_favicon_downloader,
    )
    latest_result = default_domain_metadata_uploader.get_latest_file_for_diff(
        client=remote_client
    )
    mocker.patch.object(
        default_domain_metadata_uploader, "get_latest_file_for_diff"
    ).return_value = latest_result

    (
        categories,
        unchanged_domains,
        added_domains,
        added_urls,
        subdomains,
    ) = default_domain_metadata_uploader.compare_top_picks(
        new_top_picks=json_domain_data_latest
    )

    diff_file = default_domain_metadata_uploader.create_diff_file(
        file_name=remote_blob.name,
        categories=categories,
        unchanged=unchanged_domains,
        domains=added_domains,
        urls=added_urls,
        subdomains=subdomains,
    )

    assert diff_file.startswith("Top Picks Diff File")
    assert "Newly added domains: 1" in diff_file
    assert "Domains containing subdomain: 3" in diff_file
