"""Integration tests for DomainMetadataUploader class. These tests use the testcontainers
library to emulate GCS Storage entities used by the GcsUploader class in a docker container
"""

import json
from datetime import datetime

import pytest
from google.cloud.storage import Bucket

from merino.utils.gcs.gcs_uploader import GcsUploader
from merino.utils.gcs.models import Image
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
    """Return an AsyncFaviconDownloader instance with proper async mocks"""
    # Create the base mock
    favicon_downloader = mocker.AsyncMock()

    # Mock the single download method to return an awaitable that resolves to an Image
    async def mock_download_favicon(*args, **kwargs):
        return Image(content=bytes(255), content_type="image/jpeg")

    favicon_downloader.download_favicon.side_effect = mock_download_favicon

    # Mock the multiple downloads method to return an awaitable that resolves to a list of Images
    async def mock_download_multiple_favicons(*args, **kwargs):
        return [Image(content=bytes(255), content_type="image/jpeg")] * 4

    favicon_downloader.download_multiple_favicons.side_effect = mock_download_multiple_favicons

    # Mock the close_session method
    async def mock_close_session(*args, **kwargs):
        return None

    favicon_downloader.close_session.side_effect = mock_close_session

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


def test_upload_top_picks(gcs_storage_client, gcs_storage_bucket, mock_favicon_downloader):
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
    domain_metadata_uploader = DomainMetadataUploader(
        uploader=gcp_uploader, force_upload=False, async_favicon_downloader=mock_favicon_downloader
    )

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
        async_favicon_downloader=mock_favicon_downloader,
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


def test_get_latest_file_for_diff(gcs_storage_client, gcs_storage_bucket, mock_favicon_downloader):
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
    domain_metadata_uploader = DomainMetadataUploader(
        uploader=gcp_uploader, force_upload=False, async_favicon_downloader=mock_favicon_downloader
    )

    # upload test_top_picks_1 for the 2024... file
    gcp_uploader.upload_content(json.dumps(test_top_picks_1), "20240101120555_top_picks.json")
    # upload test_top_picks_2 for the 2023... file
    gcp_uploader.upload_content(json.dumps(test_top_picks_2), "20230101120555_top_picks.json")

    # get the latest file
    latest_file = domain_metadata_uploader.get_latest_file_for_diff()

    # this should return the test_top_picks_1 since it's the latest one amongst the two files
    assert latest_file == test_top_picks_1


def test_get_latest_file_for_diff_when_no_file_is_found(
    gcs_storage_client, gcs_storage_bucket, mock_favicon_downloader
):
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
    domain_metadata_uploader = DomainMetadataUploader(
        uploader=gcp_uploader, force_upload=False, async_favicon_downloader=mock_favicon_downloader
    )

    # this should return None since we didn't upload anything to our gcs bucket
    latest_file = domain_metadata_uploader.get_latest_file_for_diff()

    assert latest_file is None


def test_destination_favicon_name(gcs_storage_client, gcs_storage_bucket, mock_favicon_downloader):
    """Test destination_favicon_name method which generates the upload path for favicons."""
    # Create uploader
    gcp_uploader = GcsUploader(
        destination_gcp_project=gcs_storage_client.project,
        destination_bucket_name=gcs_storage_bucket.name,
        destination_cdn_hostname="test_cdn_hostname",
    )

    # Create uploader instance
    domain_metadata_uploader = DomainMetadataUploader(
        uploader=gcp_uploader, force_upload=False, async_favicon_downloader=mock_favicon_downloader
    )

    # Test with different image content types
    test_cases = [
        (b"test_jpg", "image/jpeg", ".jpeg"),
        (b"test_png", "image/png", ".png"),
        (b"test_svg", "image/svg+xml", ".svg"),
        (b"test_ico", "image/x-icon", ".ico"),
        (b"test_webp", "image/webp", ".webp"),
        (b"test_gif", "image/gif", ".gif"),
        (b"test_unknown", "image/unknown", ".oct"),
    ]

    for content, content_type, expected_extension in test_cases:
        # Create an image
        test_image = Image(content=content, content_type=content_type)

        # Get the destination name
        destination_name = domain_metadata_uploader.destination_favicon_name(test_image)

        # Verify the result
        assert destination_name.startswith("favicons/")
        assert destination_name.endswith(expected_extension)
        assert str(len(content)) in destination_name

        # Verify the name contains the content hash
        import hashlib

        content_hash = hashlib.sha256(content).hexdigest()
        assert content_hash in destination_name


def test_upload_image(gcs_storage_client, gcs_storage_bucket, mock_favicon_downloader):
    """Test upload_image method which uploads a single favicon to GCS."""
    # Create uploader
    gcp_uploader = GcsUploader(
        destination_gcp_project=gcs_storage_client.project,
        destination_bucket_name=gcs_storage_bucket.name,
        destination_cdn_hostname="test_cdn_hostname",
    )

    # Create uploader instance
    domain_metadata_uploader = DomainMetadataUploader(
        uploader=gcp_uploader, force_upload=False, async_favicon_downloader=mock_favicon_downloader
    )

    # Create test image
    test_image = Image(content=b"test_image_content", content_type="image/png")

    # Generate destination name
    destination_name = domain_metadata_uploader.destination_favicon_name(test_image)

    # Upload the image
    result = domain_metadata_uploader.upload_image(
        test_image, destination_name, forced_upload=True
    )

    # Verify the result
    assert result.startswith("https://test_cdn_hostname/")
    assert destination_name in result

    # Verify the image was uploaded to GCS
    blob = gcs_storage_bucket.blob(destination_name)
    assert blob.exists()
    assert blob.download_as_bytes() == b"test_image_content"


def test_upload_favicon_with_cdn_url(
    gcs_storage_client, gcs_storage_bucket, mock_favicon_downloader
):
    """Test upload_favicon method with a URL that's already on our CDN."""
    # Create uploader
    gcp_uploader = GcsUploader(
        destination_gcp_project=gcs_storage_client.project,
        destination_bucket_name=gcs_storage_bucket.name,
        destination_cdn_hostname="test_cdn_hostname",
    )

    # Create uploader instance
    domain_metadata_uploader = DomainMetadataUploader(
        uploader=gcp_uploader, force_upload=False, async_favicon_downloader=mock_favicon_downloader
    )

    # Test with a URL that's already on our CDN
    cdn_url = f"https://{gcp_uploader.cdn_hostname}/some/path/favicon.png"

    # Call upload_favicon
    result = domain_metadata_uploader.upload_favicon(cdn_url)

    # Verify the result is the same URL (no re-upload)
    assert result == cdn_url


def test_upload_favicon_with_empty_url(gcs_storage_client, gcs_storage_bucket, mocker):
    """Test upload_favicon method with an empty URL."""
    # Create uploader
    gcp_uploader = GcsUploader(
        destination_gcp_project=gcs_storage_client.project,
        destination_bucket_name=gcs_storage_bucket.name,
        destination_cdn_hostname="test_cdn_hostname",
    )

    # Create a more specific mock favicon downloader that respects the URL value
    mock_favicon_downloader = mocker.AsyncMock()

    async def mock_download_favicon(url):
        # Return None for empty URLs
        if not url:
            return None
        return Image(content=bytes(255), content_type="image/jpeg")

    mock_favicon_downloader.download_favicon.side_effect = mock_download_favicon

    # Create uploader instance
    domain_metadata_uploader = DomainMetadataUploader(
        uploader=gcp_uploader, force_upload=False, async_favicon_downloader=mock_favicon_downloader
    )

    # Call upload_favicon with an empty URL
    result = domain_metadata_uploader.upload_favicon("")

    # Verify the result is an empty string
    assert result == ""


def test_upload_favicon_download_failure(gcs_storage_client, gcs_storage_bucket, mocker):
    """Test upload_favicon method when download fails."""
    # Create uploader
    gcp_uploader = GcsUploader(
        destination_gcp_project=gcs_storage_client.project,
        destination_bucket_name=gcs_storage_bucket.name,
        destination_cdn_hostname="test_cdn_hostname",
    )

    # Create a mock favicon downloader that returns None (failed download)
    mock_favicon_downloader = mocker.AsyncMock()

    async def mock_download_favicon(*args, **kwargs):
        return None  # Simulate download failure

    mock_favicon_downloader.download_favicon.side_effect = mock_download_favicon

    # Create uploader instance
    domain_metadata_uploader = DomainMetadataUploader(
        uploader=gcp_uploader, force_upload=False, async_favicon_downloader=mock_favicon_downloader
    )

    # Call upload_favicon with a URL that will fail to download
    result = domain_metadata_uploader.upload_favicon("https://example.com/favicon.png")

    # Verify the result is an empty string
    assert result == ""
    # Verify the download was attempted
    mock_favicon_downloader.download_favicon.assert_called_once_with(
        "https://example.com/favicon.png"
    )


def test_upload_favicon_upload_failure(gcs_storage_client, gcs_storage_bucket, mocker):
    """Test upload_favicon method when upload fails."""
    # Create uploader
    gcp_uploader = GcsUploader(
        destination_gcp_project=gcs_storage_client.project,
        destination_bucket_name=gcs_storage_bucket.name,
        destination_cdn_hostname="test_cdn_hostname",
    )

    # Create a mock favicon downloader that returns an image
    mock_favicon_downloader = mocker.AsyncMock()

    async def mock_download_favicon(*args, **kwargs):
        return Image(content=b"test_image", content_type="image/png")

    mock_favicon_downloader.download_favicon.side_effect = mock_download_favicon

    # Make the upload fail
    mocker.patch.object(gcp_uploader, "upload_image", side_effect=Exception("Upload failed"))

    # Create uploader instance
    domain_metadata_uploader = DomainMetadataUploader(
        uploader=gcp_uploader, force_upload=False, async_favicon_downloader=mock_favicon_downloader
    )

    # Call upload_favicon
    result = domain_metadata_uploader.upload_favicon("https://example.com/favicon.png")

    # Verify the result is an empty string (upload failed)
    assert result == ""


def test_upload_favicons_with_mixed_results(gcs_storage_client, gcs_storage_bucket, mocker):
    """Test upload_favicons method with some successful and some failed uploads."""
    # Create uploader
    gcp_uploader = GcsUploader(
        destination_gcp_project=gcs_storage_client.project,
        destination_bucket_name=gcs_storage_bucket.name,
        destination_cdn_hostname="test_cdn_hostname",
    )

    # Create a partial mock of DomainMetadataUploader to control upload_favicon behavior
    domain_metadata_uploader = DomainMetadataUploader(
        uploader=gcp_uploader, force_upload=False, async_favicon_downloader=mocker.AsyncMock()
    )

    # Mock upload_favicon to return different results based on input
    def mock_upload_favicon(url):
        if "success" in url:
            return f"https://test_cdn_hostname/{url}"
        else:
            return ""

    # Apply the mock
    mocker.patch.object(
        domain_metadata_uploader, "upload_favicon", side_effect=mock_upload_favicon
    )

    # Test with a mix of URLs
    test_favicons = ["success1.png", "fail1.png", "success2.png", "fail2.png"]

    # Call upload_favicons
    results = domain_metadata_uploader.upload_favicons(test_favicons)

    # Verify the results
    assert len(results) == 4
    assert results[0] == "https://test_cdn_hostname/success1.png"
    assert results[1] == ""
    assert results[2] == "https://test_cdn_hostname/success2.png"
    assert results[3] == ""

    # Verify all URLs were processed
    assert domain_metadata_uploader.upload_favicon.call_count == 4
