# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Module for test configurations for the v1 integration test directory."""

import asyncio
from typing import Any, Callable, Coroutine

import pytest_asyncio

from merino.configs import settings
from merino.main import app
from merino.providers import get_providers
from merino.providers.base import BaseProvider
from tests.integration.api.v1.types import (
    Providers,
    SetupProvidersFixture,
    TeardownProvidersFixture,
)

ProviderFactory = tuple[Providers, list[BaseProvider]]


def get_provider_factory(
    providers: Providers,
) -> Callable[..., Coroutine[Any, Any, ProviderFactory]]:
    """Return a callable that builds and initializes the given providers"""

    async def provider_factory() -> ProviderFactory:
        await asyncio.gather(*[p.initialize() for p in providers.values()])
        default_providers = [p for p in providers.values() if p.enabled_by_default]
        return providers, default_providers

    return provider_factory


@pytest_asyncio.fixture(name="setup_providers")
def fixture_setup_providers() -> SetupProvidersFixture:
    """Return a function that sets application provider dependency overrides"""

    def setup_providers(providers: Providers) -> None:
        """Set application provider dependency overrides"""
        app.dependency_overrides[get_providers] = get_provider_factory(providers)

    return setup_providers


@pytest_asyncio.fixture(name="teardown_providers")
def fixture_teardown_providers() -> TeardownProvidersFixture:
    """Return a function that resets application provider dependency overrides"""

    async def teardown_providers(providers: Providers) -> None:
        """Reset application provider dependency overrides"""
        for p in providers.values():
            await p.shutdown()
        del app.dependency_overrides[get_providers]

    return teardown_providers


@pytest_asyncio.fixture(name="inject_providers", autouse=True)
async def fixture_inject_providers(
    setup_providers: SetupProvidersFixture,
    teardown_providers: TeardownProvidersFixture,
    providers: Providers,
    disabled_providers=settings.runtime.disabled_providers,
):
    """Set up and teardown the given providers.

    Test modules or functions are expected to define the providers by creating a
    fixture named `providers` in a module and/or specifying providers for an
    individual test function by setting `providers` via the
    @pytest.mark.parametrize marker.

    For example:

    @pytest.fixture(name="providers")
    def fixture_providers() -> Providers:
        return {
            "sponsored-provider": SponsoredProvider(enabled_by_default=True),
            "nonsponsored-provider": NonsponsoredProvider(enabled_by_default=True),
        }

    or

    @pytest.mark.parametrize(
        "providers",
        [
            {
                "sponsored-provider": SponsoredProvider(enabled_by_default=True),
                "nonsponsored-provider": NonsponsoredProvider(enabled_by_default=True),
            }
        ],
    )
    """
    # Ensures this test interface takes into account disabled providers.
    enabled_providers = {k: v for k, v in providers.items() if k not in disabled_providers}
    setup_providers(enabled_providers)
    yield
    await teardown_providers(providers)
