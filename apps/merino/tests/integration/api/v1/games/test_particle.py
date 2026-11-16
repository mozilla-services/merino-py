# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Integration tests for the Particle game endpoints.

Every test runs against both the widgets route and the regular route it's replacing, which
must serve identical responses until the regular alias is removed (DISCO-4604).
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from merino.configs import settings
from merino.providers.games.particle.backends.protocol import Particle

CACHE_CONTROL = f"private, max-age={settings.games_providers.particle.cache_ttl}"


@pytest.fixture(
    name="particle_url",
    params=[
        "/api/v1/widgets/games/particle",
        # TODO(DISCO-4604): Drop the regular alias.
        "/api/v1/games/particle",
    ],
    ids=["widgets", "regular"],
)
def fixture_particle_url(request: pytest.FixtureRequest) -> str:
    """Return each Particle game route."""
    return str(request.param)


def test_particle_returns_the_game_url(
    client: TestClient, particle_url: str, particle_provider: Any
) -> None:
    """Serves the public game URL with a private Cache-Control header."""
    particle_provider.get_game_url.return_value = Particle(url="https://cdn.test/particle/")

    response = client.get(particle_url)

    assert response.status_code == 200
    assert response.json() == {"url": "https://cdn.test/particle/"}
    assert response.headers["cache-control"] == CACHE_CONTROL


def test_particle_returns_null_when_no_game_is_available(
    client: TestClient, particle_url: str, particle_provider: Any
) -> None:
    """Serves a null body when the provider has no game data."""
    particle_provider.get_game_url.return_value = None

    response = client.get(particle_url)

    assert response.status_code == 200
    assert response.json() is None
    assert response.headers["cache-control"] == CACHE_CONTROL


def test_particle_returns_null_when_the_provider_fails(
    client: TestClient, particle_url: str, particle_provider: Any
) -> None:
    """Serves a null body instead of an error when fetching the game raises."""
    particle_provider.get_game_url.side_effect = RuntimeError("boom")

    response = client.get(particle_url)

    assert response.status_code == 200
    assert response.json() is None
