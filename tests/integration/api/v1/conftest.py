# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import asyncio
from typing import Any, Callable, Coroutine

import pytest

from merino.main import app
from merino.providers import get_providers
from merino.providers.base import BaseProvider
from tests.integration.api.v1.types import (
    SetupProvidersFixture,
    TeardownProvidersFixture,
)


def get_provider_factory(
    providers: dict[str, BaseProvider]
) -> Callable[
    ..., Coroutine[Any, Any, tuple[dict[str, BaseProvider], list[BaseProvider]]]
]:
    """Return a callable that builds and initializes the given providers"""

    async def provider_factory() -> tuple[dict[str, BaseProvider], list[BaseProvider]]:
        await asyncio.gather(*[p.initialize() for p in providers.values()])
        default_providers = [p for p in providers.values() if p.enabled_by_default]
        return providers, default_providers

    return provider_factory


@pytest.fixture(name="setup_providers")
def fixture_setup_providers() -> SetupProvidersFixture:
    """Return a function that sets application provider dependency overrides"""

    def setup_providers(providers: dict[str, BaseProvider]) -> None:
        """Set application provider dependency overrides"""
        app.dependency_overrides[get_providers] = get_provider_factory(providers)

    return setup_providers


@pytest.fixture(name="teardown_providers")
def fixture_teardown_providers() -> TeardownProvidersFixture:
    """Return a function that resets application provider dependency overrides"""

    def teardown_providers() -> None:
        """Reset application provider dependency overrides"""
        del app.dependency_overrides[get_providers]

    return teardown_providers
