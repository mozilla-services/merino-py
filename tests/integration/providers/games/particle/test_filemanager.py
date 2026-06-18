"""Integration tests for the Particle file manager classes."""

import json
import pytest

from google.cloud.storage import Blob, Bucket
from unittest.mock import patch

from merino.utils.gcs.gcs_uploader import GcsUploader

from merino.providers.games.particle.backends.filemanager import (
    ParticleRemoteFileManager,
)


GREEN_DEPLOYMENT_FOLDER = "green_deployment"


@pytest.fixture(scope="function")
def gcs_storage_bucket(gcs_storage_client) -> Bucket:
    """Return a test google storage bucket object to be used by all tests. Delete it
    after each test run to ensure isolation
    """
    bucket: Bucket = gcs_storage_client.create_bucket("merino-images-local")

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


@pytest.fixture(name="remote_manifest_json")
def fixture_remote_manifest_json():
    """Load manifest data from local file into JSON - simulates data downloaed from Particle endpoint and converted to JSON."""
    with open("tests/data/games/particle/runtime-manifest.v1.json") as f:
        return json.load(f)


@pytest.fixture
def remote_filemanager(gcs_client) -> ParticleRemoteFileManager:
    """Return a ParticleRemoteFileManager instance."""
    return ParticleRemoteFileManager(
        gcs_client=gcs_client,
        manifest_file_name="test-manifest.json",
        green_deployment_folder=GREEN_DEPLOYMENT_FOLDER,
    )


class TestRemoteFileManagerUploadFile:
    """Tests against the upload_file method of ParticleRemoteFileManager."""

    @pytest.mark.asyncio
    async def test_successful_upload(self, remote_filemanager):
        """Verify a successful upload."""
        blob_name = await remote_filemanager.upload_file(
            file_name="images/image.jpg",
            file_path="tests/data/games/particle/image.jpg",
            content_type="image/jpeg",
        )

        assert blob_name == f"{GREEN_DEPLOYMENT_FOLDER}/images/image.jpg"

    @pytest.mark.asyncio
    async def test_unsuccessful_upload(self, remote_filemanager):
        """Verify an unsuccessful upload."""
        with patch.object(
            remote_filemanager.gcs_client, "upload_from_filename"
        ) as mock_upload_from_filename:
            mock_upload_from_filename.side_effect = [Exception("forced exception")]

            blob_name = await remote_filemanager.upload_file(
                file_name="images/image.jpg",
                file_path="/tests/data/games/image.jpg",
                content_type="image/jpeg",
            )

            assert blob_name == ""


class TestRemoteFileManagerUploadManifest:
    """Tests against the upload_manifest method of ParticleRemoteFileManager."""

    @pytest.mark.asyncio
    async def test_success(self, remote_filemanager, remote_manifest_json):
        """Verify a successful upload."""
        # actually uploads the json provided to the test GCS buckett
        assert await remote_filemanager.upload_manifest(remote_manifest_json)

    @pytest.mark.asyncio
    async def test_failure_blob_not_uploaded(
        self, gcs_storage_bucket, remote_filemanager, remote_manifest_json
    ):
        """Verify a failed upload."""
        with patch.object(remote_filemanager.gcs_client, "upload_content") as mock_upload_content:
            # returns a Blob without an id, which should fail the call
            mock_upload_content.return_value = Blob(
                name=remote_filemanager.manifest_file_name, bucket=gcs_storage_bucket
            )

            assert not await remote_filemanager.upload_manifest(remote_manifest_json)
