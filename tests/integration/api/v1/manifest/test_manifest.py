"""Integration tests for the /manifest endpoint using testcontainers"""

import asyncio
import orjson
import pytest

from merino.main import app
from merino.providers.manifest.backends.protocol import ManifestData
from merino.providers.manifest.provider import Provider
from merino.providers.manifest import get_provider, init_provider
from merino.web.api_v1 import router


@pytest.fixture(autouse=True, name="cleanup")
def cleanup_tasks_fixture():
    """Return a method that cleans up existing cron tasks after initialization"""

    async def cleanup_tasks(provider: Provider):
        """Cleanup cron tasks after initialization and data fetch"""
        if provider.cron_task:
            provider.cron_task.cancel()
            try:
                await provider.cron_task
            except asyncio.CancelledError:
                pass

    return cleanup_tasks


@pytest.mark.asyncio
async def test_get_manifest_success(client, gcp_uploader, mock_manifest, cleanup):
    """Uploads a manifest to the gcs bucket and verifies that the endpoint returns the uploaded file."""
    # initialize provider on startup
    await init_provider()

    # set up the endpoint
    app.include_router(router, prefix="/api/v1")

    # upload a manifest file to GCS test container
    gcp_uploader.upload_content(orjson.dumps(mock_manifest), "top_picks_latest.json")

    provider = get_provider()
    await provider.data_fetched_event.wait()

    cleanup(provider)

    response = client.get("/api/v1/manifest")
    assert response.status_code == 200

    manifest = ManifestData(**response.json())
    assert len(manifest.domains) == 1
    assert manifest.domains[0].domain == "spotify"

    assert "Cache-Control" in response.headers


@pytest.mark.asyncio
async def test_get_manifest_from_gcs_bucket_should_return_empty_manifest_file(client, cleanup):
    """Does not upload any manifests to the gcs bucket. Should return none and a 404."""
    await init_provider()

    # set up the endpoint
    app.include_router(router, prefix="/api/v1")

    provider = get_provider()
    await provider.data_fetched_event.wait()

    cleanup(provider)

    response = client.get("/api/v1/manifest")
    assert response.status_code == 404

    assert response.json()["domains"] == []
    assert "Cache-Control" not in response.headers
