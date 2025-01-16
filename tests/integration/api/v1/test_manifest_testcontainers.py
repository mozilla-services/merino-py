"""Integration tests for the /manifest endpoint, including metrics injection."""

import json
import logging
from pytest_mock import MockerFixture

import pytest
from typing import Generator
from fastapi import FastAPI
from fastapi.testclient import TestClient
from google.cloud.storage import Bucket

from aiodogstatsd import Client
from merino.middleware import ScopeKey
from merino.utils.gcs.gcp_uploader import GcsUploader, get_gcs_uploader_for_manifest
from merino.web.api_v1 import router
from merino.web.models_v1 import Manifest

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

test_app = FastAPI()
test_app.include_router(router, prefix="/api/v1")


class NoOpMetricsClient(Client):
    """Create a no-op metrics client for test usage.

    This class inherits from `aiodogstatsd.Client`, but overrides `increment` and
    `timeit` so they do nothing. This prevents KeyErrors or real metric calls in tests.
    """

    def increment(self, *args, **kwargs):
        """Do nothing instead of sending a metric increment."""
        pass

    def gauge(self, *args, **kwargs):
        """Do nothing instead of sending a metric gauge."""
        pass

    def timeit(self, *args, **kwargs):
        """Return a no-op context manager instead of timing anything."""
        from contextlib import nullcontext

        return nullcontext()


@pytest.fixture(scope="module")
def client_with_metrics() -> Generator[TestClient, None, None]:
    """Wrap `test_app` in an ASGI function that inserts a
    NoOpMetricsClient into the request scope, so that any endpoint referencing
    `request.scope[ScopeKey.METRICS_CLIENT]` won't crash.
    """

    async def asgi_wrapper(scope, receive, send):
        """Insert NoOpMetricsClient into the scope, then call the real app."""
        scope[ScopeKey.METRICS_CLIENT] = NoOpMetricsClient()
        await test_app(scope, receive, send)

    with TestClient(asgi_wrapper) as client:
        yield client


@pytest.fixture(scope="function")
def gcs_storage_bucket(gcs_storage_client) -> Generator[Bucket, None, None]:
    """Return a test google storage bucket object to be used by all tests. Delete it
    after each test run to ensure isolation
    """
    bucket: Bucket = gcs_storage_client.create_bucket("test_gcp_uploader_bucket")

    # Yield the bucket object for the test to use
    yield bucket

    # Force delete allows us to delete the bucket even if it has blobs in it
    bucket.delete(force=True)


def test_get_manifest_from_gcs_bucket(client_with_metrics,gcs_storage_bucket, gcs_storage_client, mocker: MockerFixture):
    """TODO"""
    mock_manifest_1 = {
        "domains": [
            {
                "rank": 1,
                "domain": "google",
                "categories": ["Search Engines"],
                "serp_categories": [0],
                "url": "https://www.google.com",
                "title": "Google",
                "icon": "chrome://activity-stream/content/data/content/tippytop/images/google-com@2x.png",
            }
        ]
    }
    mock_manifest_2 = {
        "domains": [
            {
                "rank": 1,
                "domain": "spotify",
                "categories": ["Entertainment"],
                "serp_categories": [0],
                "url": "https://www.spotify.com",
                "title": "Spotify",
                "icon": "chrome://activity-stream/content/data/content/tippytop/images/google-com@2x.png",
            }
        ]
    }

    # create a GcsUploader instance
    test_gcp_uploader = GcsUploader(
        destination_gcp_project=gcs_storage_client.project,
        destination_bucket_name=gcs_storage_bucket.name,
        destination_cdn_hostname="",
    )

    # override the dependency gcp uploader with the test one
    test_app.dependency_overrides[get_gcs_uploader_for_manifest] = lambda: test_gcp_uploader

    # upload the two manifest files, one for 2024 and another for 2025
    test_gcp_uploader.upload_content(json.dumps(mock_manifest_1), "20240101120555_top_picks.json")
    test_gcp_uploader.upload_content(json.dumps(mock_manifest_2), "20250101120555_top_picks.json")

    # should return the 2025 manifest with spotify
    try:
        response = client_with_metrics.get("/api/v1/manifest")
        assert response.status_code == 200

        manifest = Manifest(**response.json())
        assert len(manifest.domains) == 1
        assert manifest.domains[0].domain == "spotify"

        assert "Cache-Control" in response.headers

    finally:
        test_app.dependency_overrides.clear()
