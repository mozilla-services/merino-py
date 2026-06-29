"""Pytest fixtures for Google Cloud Storage (GCS)"""

import logging
import os

import pytest
from google.auth.credentials import AnonymousCredentials
from google.cloud.storage import Client, Bucket
from testcontainers.core.container import DockerContainer
from testcontainers.core.wait_strategies import LogMessageWaitStrategy

logger = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def gcs_storage_container() -> DockerContainer:
    """Create and return a docker container for google cloud storage entities. Tear it down
    after all the tests have finished running
    """
    logger.info("Starting up GCS storage container")

    os.environ.setdefault("STORAGE_EMULATOR_HOST", "http://localhost:4443")

    # create a docker container using the `fake-gcs-server` image, waiting for it
    # to emit its startup log line before the fixture proceeds
    container = (
        DockerContainer("fsouza/fake-gcs-server")
        .with_command("-scheme http")
        .with_bind_ports(4443, 4443)
        .waiting_for(LogMessageWaitStrategy("server started at"))
    ).start()

    port = container.get_exposed_port(4443)

    logger.info(f"\n GCS server started on port: {port}")
    yield container

    container.stop()
    logger.info("\n GCS storage container stopped")


@pytest.fixture(scope="module")
def gcs_storage_client(gcs_storage_container) -> Client:
    """Return a test google storage client object to be used by all tests and close it
    after this test suite has finished running
    """
    client: Client = Client(
        credentials=AnonymousCredentials(),  # type: ignore
        project="test_gcp_uploader_project",
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
