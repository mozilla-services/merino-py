"""Integration tests for the Particle file manager classes."""

import pytest

from google.cloud.storage import Bucket
from unittest.mock import AsyncMock, patch

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


@pytest.fixture
def remote_filemanager(gcs_client) -> ParticleRemoteFileManager:
    """Return a ParticleRemoteFileManager instance."""
    return ParticleRemoteFileManager(
        gcs_client=gcs_client,
        manifest_file_name="test-manifest.json",
        green_deployment_folder=GREEN_DEPLOYMENT_FOLDER,
    )


class TestRemoteFileManagerUploadFile:
    """Tests against the upload_file method of the ParticleRemoteFileManager."""

    @pytest.mark.asyncio
    async def test_successful_upload(self, remote_filemanager):
        """Verify a successful upload."""
        blob_name = await remote_filemanager.upload_file(
            file_name="image.jpg",
            file_path="tests/data/games/particle/image.jpg",
            content_type="image/jpeg",
        )

        assert blob_name == f"{GREEN_DEPLOYMENT_FOLDER}/image.jpg"

    @pytest.mark.asyncio
    async def test_unsuccessful_upload(self, remote_filemanager):
        """Verify an unsuccessful upload."""
        with patch.object(
            remote_filemanager.gcs_client, "upload_from_filename", new_callable=AsyncMock
        ) as mock_upload_from_filename:
            mock_upload_from_filename.side_effect = [Exception("forced exception")]

            blob_name = await remote_filemanager.upload_file(
                file_name="image.jpg",
                file_path="/tests/data/games/image.jpg",
                content_type="image/jpeg",
            )

            assert blob_name == ""
