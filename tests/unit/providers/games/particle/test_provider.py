# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the Particle games provider."""

import pytest
from pytest_mock import MockerFixture

from merino.providers.games.particle.backends.protocol import (
    Particle,
    ParticleBackend,
)
from merino.providers.games.particle.provider import Provider


test_game_url = "https://test.test"


@pytest.fixture(name="backend_mock")
def fixture_backend_mock(mocker: MockerFixture):
    """Return a mock ParticleBackend."""
    return mocker.AsyncMock(spec=ParticleBackend)


@pytest.fixture(name="provider")
def fixture_provider(statsd_mock, backend_mock: ParticleBackend) -> Provider:
    """Return a Provider instance for testing."""
    return Provider(
        backend=backend_mock,
        metrics_client=statsd_mock,
        name="particle",
        enabled_by_default=False,
    )


@pytest.fixture(name="test_particle")
def fixture_test_particle() -> Particle:
    """Return a test Particle instance."""
    return Particle(url=test_game_url)


def test_provider_name(provider: Provider) -> None:
    """Test that the provider name is set correctly."""
    assert provider.name == "particle"


def test_provider_enabled_by_default(provider: Provider) -> None:
    """Test that enabled_by_default is set correctly."""
    assert provider._enabled_by_default is False


@pytest.mark.asyncio
async def test_initialize(provider: Provider) -> None:
    """Test that initialize completes without error."""
    await provider.initialize()


@pytest.mark.asyncio
async def test_get_game_url_returns_none_when_backend_returns_none(
    provider: Provider, backend_mock
) -> None:
    """Test that get_game_url returns an empty Particle when backend returns None."""
    backend_mock.get_game_url.return_value = None

    particle = await provider.get_game_url()

    assert particle is None


@pytest.mark.asyncio
async def test_get_game_url_returns_correct_potd(
    provider: Provider, backend_mock, test_particle
) -> None:
    """Test that get_game_url returns a correct Particle instance."""
    backend_mock.get_game_url.return_value = test_particle

    particle = await provider.get_game_url()

    assert particle is not None
    assert particle.url == test_game_url
