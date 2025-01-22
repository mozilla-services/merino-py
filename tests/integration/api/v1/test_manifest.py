"""Integration tests for the /manifest endpoint, including metrics injection."""

import json
from unittest.mock import Mock
from google.cloud.storage import Blob
from merino.main import app
from merino.utils.gcs.gcp_uploader import GcsUploader, get_gcs_uploader_for_manifest
from merino.web.models_v1 import Manifest


def test_get_manifest_success(client_with_metrics, mock_manifest_2024):
    """Test successful manifest retrieval with metrics client."""
    mock_uploader = Mock(spec=GcsUploader)
    mock_blob = Mock(spec=Blob)
    mock_blob.name = "20240110_top_picks.json"
    mock_blob.download_as_text.return_value = json.dumps(mock_manifest_2024)
    mock_uploader.get_most_recent_file.return_value = mock_blob

    app.dependency_overrides[get_gcs_uploader_for_manifest] = lambda: mock_uploader

    try:
        response = client_with_metrics.get("/api/v1/manifest")
        assert response.status_code == 200

        manifest = Manifest(**response.json())
        assert len(manifest.domains) == 1
        assert manifest.domains[0].domain == "google"
        assert "Cache-Control" in response.headers

    finally:
        app.dependency_overrides.clear()
