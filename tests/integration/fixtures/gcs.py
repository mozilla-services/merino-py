"""Pytest fixtures for Google Cloud Storage (GCS)"""

import logging
import os

import pytest
from google.auth.credentials import AnonymousCredentials
from google.cloud.storage import Client
from testcontainers.core.container import DockerContainer
from testcontainers.core.waiting_utils import wait_for_logs

logger = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def gcs_storage_container() -> DockerContainer:
    """Create and return a docker container for google cloud storage entities. Tear it down
    after all the tests have finished running
    """
    logger.info("Starting up GCS storage container")

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

    logger.info(f"\n GCS server started with delay: {delay} seconds on port: {port}")
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
