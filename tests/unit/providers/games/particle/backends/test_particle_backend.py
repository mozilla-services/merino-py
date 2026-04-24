# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the Particle backend."""

import logging
import pytest

from httpx import AsyncClient, Request, Response
from pytest import LogCaptureFixture
from pytest_mock import MockerFixture
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

from merino.configs import settings
from merino.utils.gcs.gcs_uploader import GcsUploader
from merino.providers.games.particle.backends.particle import ParticleBackend

_game_url = settings.games_providers.particle.game_url

# these values don't really matter, as the http calls are mocked
PARTICLE_URL_ROOT = "http://test.com"
PARTICLE_URL_PATH_MANIFEST = "/manifest.v1.json"


# FIXTURES
@pytest.fixture()
def valid_manifest_data():
    """Load mock response data from the Particle manifest endpoint."""
    with open("tests/data/games/particle/runtime-manifest.v1.json") as f:
        return f.read()


@pytest.fixture(name="gcs_uploader_mock")
def fixture_gcs_uploader_mock() -> GcsUploader:
    """Return a mock GcsUploader."""
    return MagicMock(spec=GcsUploader)


@pytest.fixture(name="backend")
def fixture_backend(
    gcs_uploader_mock: GcsUploader, mocker: MockerFixture, statsd_mock
) -> ParticleBackend:
    """Return a WikimediaPotdBackend instance for testing."""
    return ParticleBackend(
        gcs_uploader=gcs_uploader_mock,
        http_client=mocker.AsyncMock(spec=AsyncClient),
        metrics_client=statsd_mock,
        particle_url_root=PARTICLE_URL_ROOT,
        particle_url_path_manifest=PARTICLE_URL_PATH_MANIFEST,
    )


# END FIXTURES


# BEGIN get_game_url TESTS
@pytest.mark.asyncio
async def test_get_game_url_returns_correct_particle(backend: ParticleBackend) -> None:
    """Test that get_game_url returns the expected game URL value."""
    result = await backend.get_game_url()

    assert result is not None
    assert result.url == _game_url


# END get_game_url TESTS


# BEGIN _fetch_manifest_json TESTS
@pytest.mark.asyncio
async def test_fetch_manifest_json_returns_json(
    valid_manifest_data, backend: ParticleBackend
) -> None:
    """Test fetching manifest JSON succeeds along happy path."""
    client_mock: AsyncMock = cast(AsyncMock, backend.http_client)
    client_mock.get.return_value = Response(
        status_code=200,
        content=valid_manifest_data,
        request=Request(method="GET", url=PARTICLE_URL_ROOT),
    )

    result = await backend._fetch_manifest_json()

    # result should be a python object (result of json.loads)
    assert isinstance(result, object)


@pytest.mark.asyncio
async def test_fetch_manifest_json_returns_none_for_invalid_json(
    backend: ParticleBackend, caplog: LogCaptureFixture, filter_caplog: Any
):
    """Test fetching invalid manifest JSON returns None."""
    client_mock: AsyncMock = cast(AsyncMock, backend.http_client)
    client_mock.get.return_value = Response(
        status_code=200,
        # foo below isn't double quoted, so json conversion fails
        content="{foo: 1}",
        request=Request(method="GET", url=PARTICLE_URL_ROOT),
    )

    caplog.set_level(logging.ERROR)

    result = await backend._fetch_manifest_json()

    # get error records
    error_records = filter_caplog(
        caplog.records,
        "merino.providers.games.particle.backends.particle",
    )

    # verify result is None and expected error was logged
    assert result is None
    assert len(error_records) == 1
    assert "JSON error when converting Particle response" == error_records[0].message


@pytest.mark.asyncio
async def test_fetch_manifest_json_returns_none_for_http_error(
    backend: ParticleBackend, caplog: LogCaptureFixture, filter_caplog: Any
):
    """Test fetching invalid manifest JSON returns None."""
    client_mock: AsyncMock = cast(AsyncMock, backend.http_client)
    client_mock.get.return_value = Response(
        status_code=500, request=Request(method="GET", url=PARTICLE_URL_ROOT)
    )

    caplog.set_level(logging.ERROR)

    result = await backend._fetch_manifest_json()

    # get error records
    error_records = filter_caplog(
        caplog.records,
        "merino.providers.games.particle.backends.particle",
    )

    # make sure result is None and expected error has been logged
    assert result is None
    assert len(error_records) == 1
    assert "HTTP error when fetching Particle manifest" in error_records[0].message


# END _fetch_manifest_json TESTS
