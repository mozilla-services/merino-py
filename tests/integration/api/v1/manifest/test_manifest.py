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


async def _prime_manifest(gcp_uploader, mock_manifest, cleanup) -> Provider:
    """Upload a manifest to the fake GCS bucket and wait for the provider to load it.

    Returns the initialized provider so tests can inspect state if needed.
    """
    await init_provider()
    app.include_router(router, prefix="/api/v1")

    gcp_uploader.upload_content(orjson.dumps(mock_manifest), "top_picks_latest.json")

    provider = get_provider()
    await provider.data_fetched_event.wait()
    cleanup(provider)
    return provider


@pytest.mark.asyncio
async def test_get_manifest_success(client, gcp_uploader, mock_manifest, cleanup):
    """Uploads a manifest to the gcs bucket and verifies that the endpoint returns the uploaded file."""
    await _prime_manifest(gcp_uploader, mock_manifest, cleanup)

    response = client.get("/api/v1/manifest")
    assert response.status_code == 200

    manifest = ManifestData(**response.json())
    assert len(manifest.domains) == 1
    assert manifest.domains[0].domain == "spotify"

    assert "Cache-Control" in response.headers
    assert "ETag" in response.headers
    # Quoted per RFC 7232; the unquoted form is not a legal ETag value.
    assert response.headers["ETag"].startswith('"')
    assert response.headers["ETag"].endswith('"')


@pytest.mark.asyncio
async def test_get_manifest_returns_304_on_matching_if_none_match(
    client, gcp_uploader, mock_manifest, cleanup
):
    """A conditional request echoing the current ETag should get a bodyless 304."""
    await _prime_manifest(gcp_uploader, mock_manifest, cleanup)

    first = client.get("/api/v1/manifest")
    etag = first.headers["ETag"]

    second = client.get("/api/v1/manifest", headers={"If-None-Match": etag})

    assert second.status_code == 304
    assert second.content == b""
    assert second.headers["ETag"] == etag
    assert "Cache-Control" in second.headers


@pytest.mark.asyncio
async def test_get_manifest_returns_200_on_mismatched_if_none_match(
    client, gcp_uploader, mock_manifest, cleanup
):
    """A stale If-None-Match should fall through to a normal 200 with a fresh ETag."""
    await _prime_manifest(gcp_uploader, mock_manifest, cleanup)

    response = client.get("/api/v1/manifest", headers={"If-None-Match": '"stale-etag"'})

    assert response.status_code == 200
    manifest = ManifestData(**response.json())
    assert len(manifest.domains) == 1
    assert response.headers["ETag"] != '"stale-etag"'


@pytest.mark.asyncio
async def test_get_manifest_returns_404_when_not_loaded(client, cleanup):
    """With nothing uploaded to GCS, the endpoint should 404 with an error detail rather than
    a success-shaped empty manifest body.
    """
    await init_provider()

    # set up the endpoint
    app.include_router(router, prefix="/api/v1")

    provider = get_provider()
    await provider.data_fetched_event.wait()

    cleanup(provider)

    response = client.get("/api/v1/manifest")
    assert response.status_code == 404
    assert response.json() == {"detail": "Manifest not found"}
    assert "Cache-Control" not in response.headers
    assert "ETag" not in response.headers
