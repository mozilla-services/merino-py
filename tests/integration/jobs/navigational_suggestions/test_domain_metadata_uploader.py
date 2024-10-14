"""Integration tests for DomainMetadataUploader class. These tests use the testcontainers
library to emulate GCS Storage entities used by the GcsUploader class in a docker container
"""

import json
from datetime import datetime

import pytest
from google.cloud.storage import Bucket

from merino.content_handler.gcp_uploader import GcsUploader
from merino.content_handler.models import Image
from merino.jobs.navigational_suggestions.domain_metadata_uploader import (
    DomainMetadataUploader,
)


@pytest.fixture(scope="function")
def gcs_storage_bucket(gcs_storage_client) -> Bucket:
    """Return a test google storage bucket object to be used by all tests. Delete it
    after each test run to ensure isolation
    """
    bucket: Bucket = gcs_storage_client.create_bucket("test_gcp_uploader_bucket")

    # Yield the bucket object for the test to use
    yield bucket

    # Force delete allows us to delete the bucket even if it has blobs in it
    bucket.delete(force=True)


@pytest.fixture
def mock_favicon_downloader(mocker):
    """Return a Favicon downloader instance"""
    favicon_downloader = mocker.patch(
        "merino.jobs.navigational_suggestions.utils.FaviconDownloader"
    ).return_value

    # mocking the download method to return a Image type instead of making an actual get request
    favicon_downloader.download_favicon.return_value = Image(
        content=bytes(255), content_type="image/jpeg"
    )
    return favicon_downloader


test_top_picks_1 = {
    "domains": [
        {
            "rank": 1,
            "title": "Example",
            "domain": "example",
            "url": "https://example.com",
            "icon": "",
            "categories": ["web-browser"],
            "serp_categories": [0],
            "similars": ["exxample", "exampple", "eexample"],
        },
        {
            "rank": 2,
            "title": "Firefox",
            "domain": "firefox",
            "url": "https://firefox.com",
            "icon": "",
            "categories": ["web-browser"],
            "serp_categories": [18],
            "similars": ["firefoxx", "foyerfox", "fiirefox", "firesfox", "firefoxes"],
        },
        {
            "rank": 3,
            "title": "Mozilla",
            "domain": "mozilla",
            "url": "https://mozilla.org/en-US/",
            "icon": "",
            "categories": ["web-browser"],
            "serp_categories": [18],
            "similars": ["mozzilla", "mozila"],
        },
    ]
}

test_top_picks_2 = {
    "domains": [
        {
            "rank": 1,
            "title": "Abc",
            "domain": "abc",
            "url": "https://abc.test",
            "icon": "",
            "categories": ["web-browser"],
            "serp_categories": [0],
            "similars": ["aa", "ab", "acb"],
        },
        {
            "rank": 2,
            "title": "Banana",
            "domain": "banana",
            "url": "https://banana.test",
            "icon": "",
            "categories": ["web-browser"],
            "serp_categories": [0],
            "similars": ["banan", "bannana", "banana"],
        },
    ]
}


def test_upload_top_picks(gcs_storage_client, gcs_storage_bucket):
    """Test upload_top_picks method of DomainMetaDataUploader. This test also implicitly tests
    the underlying gcs uploader methods.
    """
    # create a GcsUploader instance
    gcp_uploader = GcsUploader(
        destination_gcp_project=gcs_storage_client.project,
        destination_bucket_name=gcs_storage_bucket.name,
        destination_cdn_hostname="test_cdn_hostname",
    )

    # create a DomainMetadataUploader instance
    domain_metadata_uploader = DomainMetadataUploader(uploader=gcp_uploader, force_upload=False)

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

    # call the upload method with a test top picks json
    uploaded_top_picks_blob = domain_metadata_uploader.upload_top_picks(
        json.dumps(test_top_picks_1)
    )

    top_picks_latest_blob = gcs_storage_bucket.get_blob("top_picks_latest.json")

    assert uploaded_top_picks_blob is not None
    assert uploaded_top_picks_blob.name.startswith(timestamp)
    assert top_picks_latest_blob is not None


def test_upload_favicons(gcs_storage_client, gcs_storage_bucket, mock_favicon_downloader):
    """Test upload_favicons method of DomainMetaDataUploader. This test uses the mocked version
    of the favicon downloader. This test also implicitly tests the underlying gcs uploader methods.
    """
    # create a GcsUploader instance
    gcp_uploader = GcsUploader(
        destination_gcp_project=gcs_storage_client.project,
        destination_bucket_name=gcs_storage_bucket.name,
        destination_cdn_hostname="test_cdn_hostname",
    )

    # create a DomainMetadataUploader instance
    domain_metadata_uploader = DomainMetadataUploader(
        uploader=gcp_uploader,
        force_upload=False,
        favicon_downloader=mock_favicon_downloader,
    )

    test_favicons = ["favicon1.jpg", "favicon2.jpg", "favicon3.jpg", "favicon4.jpg"]

    # call the upload method with a test top picks json
    uploaded_favicons = domain_metadata_uploader.upload_favicons(test_favicons)

    bucket_with_uploaded_favicons = gcp_uploader.storage_client.get_bucket(gcs_storage_bucket.name)

    assert uploaded_favicons is not None
    assert len(uploaded_favicons) == len(test_favicons)

    for favicon in uploaded_favicons:
        assert favicon.startswith("https://test_cdn_hostname")

    for favicon in bucket_with_uploaded_favicons.list_blobs():
        assert favicon.download_as_bytes() == bytes(255)


def test_get_latest_file_for_diff(gcs_storage_client, gcs_storage_bucket):
    """Test get_latest_file_for_diff method of DomainMetaDataUploader. This test also tests
    implicitly the get_latest_file_for_diff method on the GcsUploader
    """
    # create a GcsUploader instance
    gcp_uploader = GcsUploader(
        destination_gcp_project=gcs_storage_client.project,
        destination_bucket_name=gcs_storage_bucket.name,
        destination_cdn_hostname="test_cdn_hostname",
    )

    # create a DomainMetadataUploader instance
    domain_metadata_uploader = DomainMetadataUploader(uploader=gcp_uploader, force_upload=False)

    # upload test_top_picks_1 for the 2024... file
    gcp_uploader.upload_content(json.dumps(test_top_picks_1), "20240101120555_top_picks.json")
    # upload test_top_picks_2 for the 2023... file
    gcp_uploader.upload_content(json.dumps(test_top_picks_2), "20230101120555_top_picks.json")

    # get the latest file
    latest_file = domain_metadata_uploader.get_latest_file_for_diff()

    # this should return the test_top_picks_1 since it's the latest one amongst the two files
    assert latest_file == test_top_picks_1


def test_get_latest_file_for_diff_when_no_file_is_found(gcs_storage_client, gcs_storage_bucket):
    """Test get_latest_file_for_diff method of DomainMetaDataUploader. This test also tests
    implicitly the get_latest_file_for_diff method on the GcsUploader
    """
    # create a GcsUploader instance
    gcp_uploader = GcsUploader(
        destination_gcp_project=gcs_storage_client.project,
        destination_bucket_name=gcs_storage_bucket.name,
        destination_cdn_hostname="test_cdn_hostname",
    )

    # create a DomainMetadataUploader instance
    domain_metadata_uploader = DomainMetadataUploader(uploader=gcp_uploader, force_upload=False)

    # this should return None since we didn't upload anything to our gcs bucket
    latest_file = domain_metadata_uploader.get_latest_file_for_diff()

    assert latest_file is None
