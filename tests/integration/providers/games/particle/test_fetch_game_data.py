# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Integration test exercising Particle's full fetch path with a real httpx client.

This test wires a real `httpx.AsyncClient` (backed by `httpx.MockTransport`) into a
real `ParticleBackend`, then runs the real `Provider._fetch_game_data` orchestrator.
Unlike the unit tests in `tests/unit/providers/games/particle/test_provider.py` —
which mock `fetch_manifest_json_from_remote` to return a *string* — this exercise
goes through the real HTTP -> orjson.loads path inside the backend, so the value
flowing into `process_remote_particle_data` is a real `dict`. It pins the
intended end-to-end behavior: a successful manifest fetch should update
`last_successful_update_at`.
"""

import json
import logging

import httpx
import pytest
from pytest_mock import MockerFixture

from merino.providers.games.particle.backends.filemanager import (
    ParticleRemoteFileManager,
)
from merino.providers.games.particle.backends.particle import ParticleBackend
from merino.providers.games.particle.provider import Provider

logger = logging.getLogger(__name__)


_PARTICLE_URL_ROOT = "https://particle.test"
_PARTICLE_URL_PATH_MANIFEST = "/runtime-manifest.v1.json"


@pytest.fixture(name="manifest_json_str")
def fixture_manifest_json_str() -> str:
    """Return Particle's manifest payload as a raw JSON string, the same shape
    Particle's CDN would return over HTTP.
    """
    with open("tests/data/games/particle/runtime-manifest.v1.json") as f:
        return f.read()


@pytest.fixture(name="manifest_schema")
def fixture_manifest_schema() -> dict:
    """Load the JSON-schema used to validate the manifest."""
    with open("tests/data/games/particle/manifest-validation-schema.json") as f:
        return json.load(f)


@pytest.fixture(name="http_client")
def fixture_http_client(manifest_json_str: str) -> httpx.AsyncClient:
    """Build an httpx.AsyncClient backed by MockTransport that returns the
    Particle manifest JSON. This lets the *real* ParticleBackend.fetch path
    run, including its orjson.loads on the response body.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == _PARTICLE_URL_PATH_MANIFEST
        return httpx.Response(
            status_code=200,
            content=manifest_json_str.encode("utf-8"),
            headers={"content-type": "application/json"},
        )

    transport = httpx.MockTransport(handler)
    return httpx.AsyncClient(transport=transport, base_url=_PARTICLE_URL_ROOT)


@pytest.fixture(name="particle_backend")
def fixture_particle_backend(
    mocker: MockerFixture,
    http_client: httpx.AsyncClient,
    statsd_mock,
) -> ParticleBackend:
    """Build a real ParticleBackend backed by the MockTransport-wired http
    client. GCS-side dependencies are mocked because this test is exercising
    the remote-fetch -> orchestrate path, not the GCS round-trip.
    """
    remote_file_manager = mocker.MagicMock(spec=ParticleRemoteFileManager)
    # Simulate "no prior manifest stored in GCS" — first-run path.
    remote_file_manager.get_manifest_file.return_value = None

    return ParticleBackend(
        gcs_uploader=mocker.MagicMock(),
        http_client=http_client,
        manifest_gcs_file_name="runtime-manifest.v1.json",
        metrics_client=statsd_mock,
        particle_url_root=_PARTICLE_URL_ROOT,
        particle_url_path_manifest=_PARTICLE_URL_PATH_MANIFEST,
        remote_file_manager=remote_file_manager,
    )


@pytest.fixture(name="provider")
def fixture_provider(
    particle_backend: ParticleBackend,
    manifest_schema: dict,
    statsd_mock,
) -> Provider:
    """Build a real Provider wrapping the real backend."""
    return Provider(
        backend=particle_backend,
        cron_interval_sec=60,
        manifest_schema=manifest_schema,
        manifest_schema_version=1,
        metrics_client=statsd_mock,
        name="particle",
        resync_interval_sec=120,
        enabled=False,
    )


@pytest.mark.asyncio
async def test_fetch_game_data_completes_when_particle_returns_valid_manifest(
    provider: Provider,
) -> None:
    """When Particle returns a valid manifest over HTTP, _fetch_game_data
    should run end-to-end and record a successful update timestamp.

    This currently fails: ParticleBackend.fetch_manifest_json_from_remote
    already returns a parsed dict, and Provider._fetch_game_data calls
    `orjson.loads(...)` on that dict a second time. orjson.loads only accepts
    bytes/bytearray/memoryview/str, so it raises TypeError before
    process_remote_particle_data is ever reached.

    The unit tests miss this because the provider-test fixture mocks
    fetch_manifest_json_from_remote to return a *string* (f.read()), not a
    dict — masking the double-parse.
    """
    assert provider.last_successful_update_at == 0.0

    await provider._fetch_game_data()

    assert provider.last_successful_update_at > 0.0, (
        "Expected _fetch_game_data to complete successfully and record an "
        "update timestamp after a valid manifest fetch."
    )
