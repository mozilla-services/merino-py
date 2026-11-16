# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Test configurations for the games API endpoint tests."""

from typing import Any

import pytest
from pytest_mock import MockerFixture

from merino.main import app
from merino.providers.games import get_particle_provider
from merino.providers.games.particle.provider import Provider as ParticleProvider


@pytest.fixture(name="particle_provider")
def fixture_particle_provider(mocker: MockerFixture) -> Any:
    """Create a Particle provider mock object for test."""
    return mocker.AsyncMock(spec=ParticleProvider)


@pytest.fixture(name="inject_particle_provider", autouse=True)
def fixture_inject_particle_provider(particle_provider: Any):
    """Inject the Particle provider into the app for testing."""

    def get_test_particle_provider() -> ParticleProvider:
        return particle_provider  # type: ignore[no-any-return]

    app.dependency_overrides[get_particle_provider] = get_test_particle_provider
    yield
    del app.dependency_overrides[get_particle_provider]
