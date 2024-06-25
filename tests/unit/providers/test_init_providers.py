# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the __init__ provider module."""

import logging

import pytest
from pytest import LogCaptureFixture
from pytest_mock import MockerFixture

from merino.config import settings
from merino.exceptions import InvalidProviderError
from merino.providers import (
    get_providers,
    init_providers,
    load_providers,
    shutdown_providers,
)
from merino.providers.manager import ProviderType
from tests.types import FilterCaplogFixture


@pytest.mark.asyncio
async def test_init_providers() -> None:
    """Test for the `init_providers` method of the Merino providers module."""
    await init_providers()

    providers, default_providers = get_providers()

    assert providers.keys() == {provider.value for provider in ProviderType}

    assert {provider.name for provider in default_providers} == {
        provider.name for provider in providers.values() if provider.enabled_by_default
    }


@pytest.mark.parametrize("provider", ["adm", "amo", "top_picks", "wikipedia"])
@pytest.mark.asyncio
async def test_init_providers_with_disabled_provider(provider: str) -> None:
    """Test for the `init_providers`and `load_providers` methods when a provider
    is disabled through the `merino.runtime.disabled_providers` config.
    """
    await init_providers()

    providers = load_providers(disabled_providers_list=[])
    assert provider in providers.keys()

    # Add provider from parameters to block instantiation.
    providers = load_providers(disabled_providers_list=[provider])
    assert provider not in providers.keys()


@pytest.mark.asyncio
async def test_init_providers_unknown_provider_type(mocker: MockerFixture) -> None:
    """Test for the `init_providers` with an unknown provider."""
    mocker.patch.dict(settings.providers, values={"unknown-provider": {"type": "unknown-type"}})

    with pytest.raises(InvalidProviderError) as excinfo:
        await init_providers()

    assert str(excinfo.value) == "Unknown provider type: unknown-type"


@pytest.mark.asyncio
async def test_shutdown_providers(
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
) -> None:
    """Test for the `shutdown_providers` method of the Merino providers module."""
    caplog.set_level(logging.INFO)

    await init_providers()
    await shutdown_providers()

    records = filter_caplog(caplog.records, "merino.providers")

    assert len(records) == 2
    assert records[0].message == "Provider initialization completed"
    assert records[1].message == "Provider shutdown completed"

    providers = records[1].__dict__["providers"]

    assert set(providers) == {provider.value for provider in ProviderType}
