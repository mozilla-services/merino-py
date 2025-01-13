"""Tests for the manifest endpoint."""

import json
import pytest
import logging
from fastapi import FastAPI
from unittest.mock import Mock
from fastapi.testclient import TestClient
from google.cloud.storage import Blob
from merino.utils.gcs.gcp_uploader import GcsUploader, get_gcs_uploader_for_manifest
from merino.web.api_v1 import router
from merino.web.models_v1 import Manifest

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

test_app = FastAPI()
test_app.include_router(router, prefix="/api/v1")

test_client = TestClient(test_app)


@pytest.fixture
def mock_uploader():
    """Create a mock GCS uploader."""
    uploader = Mock(spec=GcsUploader)
    return uploader


def test_get_manifest_success():
    """Test that the endpoint returns a valid Manifest."""
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

    # Create a mock uploader
    mock_uploader = Mock(spec=GcsUploader)

    # Create a mock blob
    mock_blob = Mock(spec=Blob)
    mock_blob.name = "20240110_top_picks.json"
    mock_blob.download_as_text.return_value = json.dumps(mock_manifest)

    # Set up get_most_recent_file to return our mock blob
    mock_uploader.get_most_recent_file.return_value = mock_blob

    # Override the dependency
    test_app.dependency_overrides[get_gcs_uploader_for_manifest] = lambda: mock_uploader

    try:
        response = test_client.get("/api/v1/manifest")
        assert response.status_code == 200

        # Validate the shape with the typed Pydantic model
        manifest = Manifest(**response.json())  # raises ValidationError if mismatch

        # Optionally, check fields
        assert len(manifest.domains) == 1
        assert manifest.domains[0].domain == "google"

        # Check headers
        assert "Cache-Control" in response.headers

    finally:
        # Clean up
        test_app.dependency_overrides.clear()
