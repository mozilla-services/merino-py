"""Integration tests for the /manifest endpoint, including metrics injection."""

import json
import logging
from unittest.mock import Mock

import pytest
from typing import Generator
from fastapi import FastAPI
from fastapi.testclient import TestClient
from google.cloud.storage import Blob

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


@pytest.fixture
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


def test_get_manifest_success(client_with_metrics):
    """Test that the /manifest endpoint returns a valid Manifest, while
    also ensuring the request scope has a NoOpMetricsClient so it doesn't fail.
    """
    mock_manifest = {
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

    mock_uploader = Mock(spec=GcsUploader)

    mock_blob = Mock(spec=Blob)
    mock_blob.name = "20240110_top_picks.json"
    mock_blob.download_as_text.return_value = json.dumps(mock_manifest)
    mock_uploader.get_most_recent_file.return_value = mock_blob

    test_app.dependency_overrides[get_gcs_uploader_for_manifest] = lambda: mock_uploader

    try:
        response = client_with_metrics.get("/api/v1/manifest")
        assert response.status_code == 200

        manifest = Manifest(**response.json())
        assert len(manifest.domains) == 1
        assert manifest.domains[0].domain == "google"

        assert "Cache-Control" in response.headers

    finally:
        test_app.dependency_overrides.clear()
