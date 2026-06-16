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


@pytest.fixture
def gcs_client(gcs_storage_client, gcs_storage_bucket) -> GcsUploader:
    """Return a GcsUploader instance."""
    return GcsUploader(
        destination_gcp_project=gcs_storage_client.project,
        destination_bucket_name=gcs_storage_bucket.name,
        destination_cdn_hostname="test_cdn_hostname",
    )


class TestGetFileByName:
    """Tests against get_file_by_name function."""

    def test_success(self, gcs_client):
        """Verify a found blob returns said blob."""
        # put a blob in the bucket
        gcs_client.upload_from_filename(
            file_path="tests/data/games/particle/image.jpg",
            destination_name="image.jpg",
            content_type="image/jpeg",
        )

        # get the blob from the bucket
        blob = gcs_client.get_file_by_name("image.jpg")

        assert blob

    def test_missing_blob(self, gcs_client):
        """Verify a missing blob returns None."""
        assert not gcs_client.get_file_by_name("image.jpg")

    def test_empty_blob_name_returns_none(self, gcs_client):
        """Verify passing an empty string blob_name returns None."""
        assert not gcs_client.get_file_by_name("")


class TestUploadFromFilename:
    """Tests against the upload_from_filename function."""

    def test_success(self, gcs_client):
        """Verify success returns truthy (a blob)."""
        blob = gcs_client.upload_from_filename(
            file_path="tests/data/games/particle/image.jpg",
            destination_name="image.jpg",
            content_type="image/jpeg",
        )

        assert blob.name == "image.jpg"

    def test_bucket_failure(self, gcs_storage_client):
        """Verify bucket failure raises."""
        gcs_client = GcsUploader(
            destination_gcp_project=gcs_storage_client.project,
            # invalid bucket name
            destination_bucket_name="invalidBucketName",
            destination_cdn_hostname="test_cdn_hostname",
        )

        with pytest.raises(Exception):
            gcs_client.upload_from_filename(
                file_path="tests/data/games/particle/image.jpg",
                destination_name="image.jpg",
                content_type="image/jpeg",
            )

    def test_file_path_failure(self, gcs_client):
        """Verify invalid file path failure raises."""
        with pytest.raises(Exception):
            gcs_client.upload_from_filename(
                # file path is invalid
                file_path="tests/data/games/particle/missing.jpg",
                destination_name="missing.jpg",
                content_type="image/jpeg",
            )


class TestDeleteFileByName:
    """Tests against the delete_file_by_name function."""

    def test_success(self, gcs_client):
        """Verify the blob is deleted."""
        # put a file in the bucket to delete
        gcs_client.upload_from_filename(
            file_path="tests/data/games/particle/image.jpg",
            destination_name="image.jpg",
            content_type="image/jpeg",
        )

        # make sure the file exists
        blob = gcs_client.get_file_by_name("image.jpg")

        assert blob

        # delete the file
        gcs_client.delete_file_by_name("image.jpg")

        # make sure the file doesn't exist
        blob = gcs_client.get_file_by_name("image.jpg")

        assert not blob

    def test_failure(self, gcs_client):
        """Verify the blob is not deleted when an exception occurs."""
        # put a file in the bucket to delete
        gcs_client.upload_from_filename(
            file_path="tests/data/games/particle/image.jpg",
            destination_name="image.jpg",
            content_type="image/jpeg",
        )

        # make sure the file exists
        blob = gcs_client.get_file_by_name("image.jpg")

        assert blob

        with pytest.raises(Exception):
            # try to delete a file that doesn't exist
            gcs_client.delete_file_by_name("notfound.jpg")


class TestMoveFile:
    """Tests against the move_file function."""

    def test_success_no_overwrite(self, gcs_client):
        """Test successfully moving a file when it's not overwriting an existing file."""
        # put a file in the bucket to move
        blob = gcs_client.upload_from_filename(
            file_path="tests/data/games/particle/image.jpg",
            destination_name="green/image.jpg",
            content_type="image/jpeg",
        )

        # move the file
        gcs_client.move_file(blob_name="green/image.jpg", destination_name="image.jpg")

        # make sure the file was moved
        blob = gcs_client.get_file_by_name("image.jpg")

        assert blob

    def test_success_overwrite(self, gcs_client):
        """Test successfully moving a file when it's overwriting an existing file."""
        # put a file in the bucket to overwrite - the "prod" image
        prod_image = gcs_client.upload_from_filename(
            file_path="tests/data/games/particle/image.jpg",
            destination_name="image.jpg",
            content_type="image/jpeg",
        )

        prod_md5 = prod_image.md5_hash

        # put a "staging" file in the bucket to replace the above
        staging_image = gcs_client.upload_from_filename(
            file_path="tests/data/games/particle/image2.jpg",
            destination_name="green/image.jpg",
            content_type="image/jpeg",
        )

        staging_md5 = staging_image.md5_hash

        # "deploy" the staged file
        gcs_client.move_file(blob_name="green/image.jpg", destination_name="image.jpg")

        # make sure the file was moved
        blob = gcs_client.get_file_by_name("image.jpg")

        # make sure the blob is found
        assert blob

        # make sure the moved file matches the hash of the staged file
        assert blob.md5_hash == staging_md5

        # extra check to make double sure the file was actually moved
        assert prod_md5 != blob.md5_hash

    def test_failure_invalid_source(self, gcs_client):
        """Test failure when the source/staging file cannot be found."""
        # put a file in the bucket to overwrite - the "prod" image
        gcs_client.upload_from_filename(
            file_path="tests/data/games/particle/image.jpg",
            destination_name="image.jpg",
            content_type="image/jpeg",
        )

        # put a "staging" file in the bucket to replace the above
        gcs_client.upload_from_filename(
            file_path="tests/data/games/particle/image2.jpg",
            destination_name="green/image.jpg",
            content_type="image/jpeg",
        )

        with pytest.raises(Exception):
            # blob_name is invalid
            gcs_client.move_file(blob_name="blue/image.jpg", destination_name="image.jpg")


class TestUploadContent:
    """Tests against the upload_content function."""

    def test_basic_success(self, gcs_client):
        """Test basic success scenario - no overwrite/forced upload."""
        # upload basic json
        blob = gcs_client.upload_content(
            content="{}", destination_name="test.json", content_type="application/json"
        )

        # no matter what happens above, a blob is returned
        # make sure it has an id, which means it was uploaded successfully(?)
        assert blob.id

    def test_failure_by_collision(self, gcs_client):
        """Test failure scenario when the same file exists and forced_upload is False."""
        # upload basic json to overwrite
        gcs_client.upload_content(
            content="{}", destination_name="test.json", content_type="application/json"
        )

        # attempt to overwrite the basic json without forced_upload
        blob = gcs_client.upload_content(
            content="{}", destination_name="test.json", content_type="application/json"
        )

        # blob should not be uploaded
        assert not blob.id

    def test_success_with_overwrite(self, gcs_client):
        """Test success scenario with overwrite."""
        # upload basic json to overwrite
        gcs_client.upload_content(
            content="{}", destination_name="test.json", content_type="application/json"
        )

        # attempt to overwrite the basic json
        blob2 = gcs_client.upload_content(
            content="{}",
            destination_name="test.json",
            content_type="application/json",
            forced_upload=True,
        )

        assert blob2.id
