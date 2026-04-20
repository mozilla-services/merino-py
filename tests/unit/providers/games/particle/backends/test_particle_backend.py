# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the Particle backend."""

import pytest
from unittest.mock import MagicMock

from merino.configs import settings
from merino.utils.gcs.gcs_uploader import GcsUploader
from merino.providers.games.particle.backends.particle import ParticleBackend

_game_url = settings.games_providers.particle.game_url


@pytest.fixture(name="gcs_uploader_mock")
def fixture_gcs_uploader_mock() -> GcsUploader:
    """Return a mock GcsUploader."""
    return MagicMock(spec=GcsUploader)


@pytest.fixture(name="backend")
def fixture_backend(
    statsd_mock,
    gcs_uploader_mock: GcsUploader,
) -> ParticleBackend:
    """Return a WikimediaPotdBackend instance for testing."""
    return ParticleBackend(
        metrics_client=statsd_mock,
        gcs_uploader=gcs_uploader_mock,
    )


@pytest.mark.asyncio
async def test_get_pitcture_of_the_day_returns_correct_potd(backend: ParticleBackend) -> None:
    """Test that get_game_url."""
    result = await backend.get_game_url()

    assert result is not None
    assert result.url == _game_url
