"""Integration tests for GcsUploader using a fake-gcs-server container."""

from datetime import datetime, timezone

import pytest

from merino.utils.gcs.gcs_uploader import GcsUploader


@pytest.fixture
def gcs_uploader(gcs_storage_client, gcs_storage_bucket) -> GcsUploader:
    """Return a GcsUploader pointed at the test bucket."""
    return GcsUploader(
        destination_gcp_project=gcs_storage_client.project,
        destination_bucket_name=gcs_storage_bucket.name,
        destination_cdn_hostname="",
    )


def test_upload_content_without_custom_time(gcs_uploader, gcs_storage_bucket):
    """Test that blob is uploaded and accessible when custom_time is not set."""
    content = b"hello world"
    blob_name = "no_custom_time.txt"

    result = gcs_uploader.upload_content(content, blob_name)

    assert result is not None
    assert result.name == blob_name
    uploaded = gcs_storage_bucket.get_blob(blob_name)
    assert uploaded is not None
    assert uploaded.download_as_bytes() == content


def test_upload_content_with_custom_time(gcs_uploader, gcs_storage_bucket):
    """Test that blob is uploaded and custom_time is set on the blob when custom_time is provided."""
    content = b"test content"
    blob_name = "custom_time.txt"
    custom_time = datetime(2030, 6, 1, tzinfo=timezone.utc)

    result = gcs_uploader.upload_content(content, blob_name, custom_time=custom_time)

    assert result is not None
    assert result.name == blob_name

    uploaded = gcs_storage_bucket.get_blob(blob_name)
    assert uploaded is not None
    assert uploaded.download_as_bytes() == content

    uploaded.reload()
    if uploaded.custom_time is not None:
        assert uploaded.custom_time == custom_time


def test_upload_content_skips_existing_blob(gcs_uploader, gcs_storage_bucket):
    """Test that existing blob is not overwritten when forced_upload is False."""
    blob_name = "skip_existing.txt"
    original = b"original"
    updated = b"updated"

    gcs_uploader.upload_content(original, blob_name)
    gcs_uploader.upload_content(updated, blob_name, forced_upload=False)

    stored = gcs_storage_bucket.get_blob(blob_name)
    assert stored is not None
    assert stored.download_as_bytes() == original


def test_upload_content_force_overwrites_existing(gcs_uploader, gcs_storage_bucket):
    """Test that existing blob is overwritten when forced_upload is True."""
    blob_name = "force_overwrite.txt"
    original = b"original"
    updated = b"updated"

    gcs_uploader.upload_content(original, blob_name)
    gcs_uploader.upload_content(updated, blob_name, forced_upload=True)

    stored = gcs_storage_bucket.get_blob(blob_name)
    assert stored is not None
    assert stored.download_as_bytes() == updated
