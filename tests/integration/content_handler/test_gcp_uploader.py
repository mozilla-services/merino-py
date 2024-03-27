"""Integration tests for GcsUploader class using testcontainers library to emulate GCS Storage
entities in a docker container
"""
import os
from typing import Generator

import pytest
from google.auth.credentials import AnonymousCredentials
from google.cloud.storage import Bucket, Client
from testcontainers.core.container import DockerContainer
from testcontainers.core.waiting_utils import wait_for_logs

from merino.content_handler.gcp_uploader import GcsUploader
from merino.content_handler.models import Image


@pytest.fixture(scope="module")
def gcs_storage_container() -> DockerContainer:
    """Create and return a docker container for google cloud storage entities. Tear it down
    after all the tests have finished running
    """
    print("Starting up GCS storage container")

    os.environ.setdefault("STORAGE_EMULATOR_HOST", "http://localhost:4443")

    # create a docker container using the `fake-gcs-server` image
    container = (
        DockerContainer("fsouza/fake-gcs-server")
        .with_command("-scheme http")
        .with_bind_ports(4443, 4443)
    ).start()

    # wait for the container to start and emit logs
    delay = wait_for_logs(container, "server started at")
    port = container.get_exposed_port(4443)

    print(f"\n GCS server started with delay: {delay} seconds on port: {port}")
    yield container

    container.stop()
    print("\n GCS storage container stopped")


@pytest.fixture(scope="module")
def gcs_storage_client(gcs_storage_container) -> Client:
    """Return a test google storage client object to be used by all tests and close it
    after this test suite has finished running
    """
    client: Client = Client(
        credentials=AnonymousCredentials(), project="test_gcp_uploader_project"
    )

    yield client

    client.close()


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


@pytest.fixture(scope="function")
def gcp_uploader(
    gcs_storage_client, gcs_storage_bucket
) -> Generator[GcsUploader, None, None]:
    """Return a GcsUploader instance for each test"""
    uploader = GcsUploader(
        destination_gcp_project=gcs_storage_client.project,
        destination_bucket_name=gcs_storage_bucket.name,
        destination_cdn_hostname="test_cdn_hostname",
    )
    yield uploader


def test_upload_image(
    gcs_storage_container, gcs_storage_client, gcs_storage_bucket, gcp_uploader
):
    """Test upload_image method of GcsUploader. This test also tests the upload_content method
    implicitly
    """
    image_content = bytes(255)
    image_name = "test_image.jpg"
    image = Image(content=image_content, content_type="image/jpeg")

    image_url = gcp_uploader.upload_image(image, image_name)

    image_blob = gcp_uploader.storage_client.get_bucket(
        gcs_storage_bucket.name
    ).get_blob(image_name)

    assert image_blob.exists()
    assert image_url.startswith("https://test_cdn_hostname")

    download_blob = image_blob.download_as_bytes()

    assert download_blob == image_content


def test_get_most_recent_file(
    gcs_storage_container, gcs_storage_client, gcs_storage_bucket, gcp_uploader
):
    """Test get_most_recent_file method of GcsUploader. This test also tests the upload_content
    method implicitly, since we call that to upload our test files
    """
    gcp_uploader.upload_content(bytes(255), "20240101120555_top_picks.json")
    gcp_uploader.upload_content(bytes(255), "20230101120555_top_picks.json")

    blob = gcp_uploader.get_most_recent_file(exclusion="", sort_key=lambda x: x.name)

    assert blob.name == "20240101120555_top_picks.json"
