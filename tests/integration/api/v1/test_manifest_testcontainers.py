"""Integration tests for the /manifest endpoint using testcontainers"""

import orjson

from merino.main import app
from merino.utils.gcs.gcp_uploader import get_gcs_uploader_for_manifest
from merino.web.models_v1 import Manifest


def test_get_manifest_from_gcs_bucket_should_return_latest(
    client_with_metrics,
    gcp_uploader,
    mock_manifest_2024,
    mock_manifest_2025,
):
    """Uploads two manifests to the gcs bucket for 2024 and 2025. Should return the latest one a 200."""
    # set up the endpoint and override the dependency gcp uploader with the test one
    app.dependency_overrides[get_gcs_uploader_for_manifest] = lambda: gcp_uploader

    # upload the two manifest files, one for 2024 and another for 2025
    gcp_uploader.upload_content(orjson.dumps(mock_manifest_2024), "20240101120555_top_picks.json")
    gcp_uploader.upload_content(orjson.dumps(mock_manifest_2025), "20250101120555_top_picks.json")

    # should return the 2025 manifest with spotify
    try:
        response = client_with_metrics.get("/api/v1/manifest")
        assert response.status_code == 200

        manifest = Manifest(**response.json())
        assert len(manifest.domains) == 1
        assert manifest.domains[0].domain == "spotify"

        assert "Cache-Control" in response.headers

    finally:
        app.dependency_overrides.clear()


def test_get_manifest_from_gcs_bucket_should_return_none(client_with_metrics, gcp_uploader):
    """Does not upload any manifests to the gcs bucket. Should return none and a 404."""
    # set up the endpoint and override the dependency gcp uploader with the test one
    app.dependency_overrides[get_gcs_uploader_for_manifest] = lambda: gcp_uploader

    # should not return a manifest
    try:
        response = client_with_metrics.get("/api/v1/manifest")

        assert response.status_code == 404
        assert response.json()["error"] == "Manifest not found"
        assert "Cache-Control" not in response.headers

    finally:
        app.dependency_overrides.clear()
