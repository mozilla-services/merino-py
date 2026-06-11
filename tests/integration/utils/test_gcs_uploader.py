"""Integration tests for the GcsUploader class."""

import pytest

from google.cloud.storage import Bucket

from merino.utils.gcs.gcs_uploader import GcsUploader


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


class TestGetFileByName:
    """Tests against get_file_by_name function."""

    def test_success(self, gcs_storage_client, gcs_storage_bucket):
        """Verify a found blob returns said blob."""
        gcs_client = GcsUploader(
            destination_gcp_project=gcs_storage_client.project,
            destination_bucket_name=gcs_storage_bucket.name,
            destination_cdn_hostname="test_cdn_hostname",
        )

        # put a blob in the bucket
        gcs_client.upload_from_filename(
            file_path="tests/data/games/particle/image.jpg",
            destination_name="image.jpg",
            content_type="image/jpeg",
        )

        # get the blob from the bucket
        blob = gcs_client.get_file_by_name("image.jpg")

        assert blob

    def test_missing_blob(self, gcs_storage_client, gcs_storage_bucket):
        """Verify a missing blob returns None."""
        gcs_client = GcsUploader(
            destination_gcp_project=gcs_storage_client.project,
            destination_bucket_name=gcs_storage_bucket.name,
            destination_cdn_hostname="test_cdn_hostname",
        )

        assert not gcs_client.get_file_by_name("image.jpg")

    def test_empty_blob_name_returns_none(self, gcs_storage_client, gcs_storage_bucket):
        """Verify when given an empty string blob name, None is returned."""
        gcs_client = GcsUploader(
            destination_gcp_project=gcs_storage_client.project,
            destination_bucket_name=gcs_storage_bucket.name,
            destination_cdn_hostname="test_cdn_hostname",
        )

        assert not gcs_client.get_file_by_name("")


class TestUploadFromFilename:
    """Tests against the upload_from_filename function."""

    def test_success(self, gcs_storage_client, gcs_storage_bucket):
        """Verify success returns truthy (a blob)."""
        gcs_client = GcsUploader(
            destination_gcp_project=gcs_storage_client.project,
            destination_bucket_name=gcs_storage_bucket.name,
            destination_cdn_hostname="test_cdn_hostname",
        )

        blob = gcs_client.upload_from_filename(
            file_path="tests/data/games/particle/image.jpg",
            destination_name="image.jpg",
            content_type="image/jpeg",
        )

        assert blob.name == "image.jpg"

    def test_failure(self, gcs_storage_client):
        """Verify failure raises."""
        gcs_client = GcsUploader(
            destination_gcp_project=gcs_storage_client.project,
            destination_bucket_name="invalidBucketName",
            destination_cdn_hostname="test_cdn_hostname",
        )

        with pytest.raises(Exception):
            gcs_client.upload_from_filename(
                file_path="tests/data/games/particle/image.jpg",
                destination_name="image.jpg",
                content_type="image/jpeg",
            )
