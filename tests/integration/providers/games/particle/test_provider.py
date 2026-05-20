# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Integration tests for the Particle Provider"""

import json
import pytest

from httpx import AsyncClient, Request, Response
from pytest_mock import MockerFixture
from typing import cast
from unittest.mock import patch, AsyncMock

from merino.providers.games.particle.backends.particle import ParticleBackend
from merino.providers.games.particle.provider import Provider


@pytest.fixture(name="manifest_json_raw_str")
def fixture_manifest_json_raw_str() -> str:
    """Return Particle's manifest payload as a raw JSON string, mimicing actual HTTP response."""
    with open("tests/data/games/particle/runtime-manifest.v1.json") as f:
        return f.read()


@pytest.fixture(name="manifest_validation_schema")
def fixture_manifest_validation_schema():
    """Load the JSON schema used to validate the manifest."""
    with open("tests/data/games/particle/manifest-validation-schema.json") as f:
        return json.load(f)


@pytest.fixture(name="particle_backend")
def fixture_particle_backend(
    mocker: MockerFixture,
    statsd_mock,
) -> ParticleBackend:
    """Create a particle backend with a mocked http_client intended to simulate fetching data from particle"""
    return ParticleBackend(
        gcs_uploader=mocker.MagicMock(),
        http_client=mocker.AsyncMock(spec=AsyncClient),
        manifest_gcs_file_name="runtime-manifest.v1.json",
        metrics_client=statsd_mock,
        particle_url_root="https://test.test/",
        particle_url_path_manifest="manifest.json",
        remote_file_manager=mocker.MagicMock(),
    )


@pytest.fixture(name="particle_provider")
def fixture_particle_provider(
    particle_backend, manifest_json_raw_str, manifest_validation_schema, statsd_mock
):
    """Create a particle provider with a custom happy path response on the backend's http_client"""
    # customize response from the backend http client to mimic a successful
    # response from particle
    client_mock: AsyncMock = cast(AsyncMock, particle_backend.http_client)

    client_mock.get.side_effect = [
        Response(
            status_code=200,
            content=manifest_json_raw_str.encode("utf-8"),
            headers={"content-type": "application/json"},
            request=Request(
                method="GET",
                url=("https://test.test"),
            ),
        )
    ]

    return Provider(
        backend=particle_backend,
        cron_interval_sec=60,
        manifest_schema=manifest_validation_schema,
        manifest_schema_version=1,
        metrics_client=statsd_mock,
        name="particle",
        resync_interval_sec=120,
        enabled=False,
    )


@pytest.mark.asyncio
async def test_fetch_game_data_successfully_processes_valid_remote_data(particle_provider) -> None:
    """Test that fetching valid manifest data from particle succeeds"""
    with patch.object(
        particle_provider, "process_remote_particle_data", new=AsyncMock()
    ) as mock_process_remote_data:
        mock_process_remote_data.return_value = True

        # verify last update is at the default value
        assert particle_provider.last_successful_update_at == 0.0

        await particle_provider._fetch_game_data()

        # _fetch_game_data should have successfully run, updating the last update time
        assert particle_provider.last_successful_update_at > 0.0

        # a successful fetch should result in process_remote_particle_data
        # being called
        mock_process_remote_data.assert_awaited_once()
