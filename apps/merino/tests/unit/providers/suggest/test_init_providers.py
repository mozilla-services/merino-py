# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the __init__ suggest provider module."""

import logging
from unittest.mock import AsyncMock, patch

import pytest
from dynaconf.nodes import DataDict
from pytest import LogCaptureFixture
from pytest_mock import MockerFixture

from merino.configs import settings
from merino.exceptions import InvalidProviderError
from merino.providers.suggest import (
    _initialize_provider,
    get_providers,
    init_providers,
    load_providers,
    shutdown_providers,
)
from merino.providers.suggest.manager import ProviderType
from tests.types import FilterCaplogFixture

DISABLED_PROVIDERS = settings.runtime.disabled_providers


@pytest.fixture(autouse=True)
def patch_flightaware_fetch_data():
    """Patch FlightAware Provider._fetch_data to prevent real GCS calls."""
    with patch(
        "merino.providers.suggest.flightaware.provider.Provider._fetch_data",
        new_callable=AsyncMock,
    ) as mock_fetch_data:
        yield mock_fetch_data


@pytest.fixture(autouse=True)
def patch_finance_fetch_manifest():
    """Patch Finance Provider._fetch_manifest to prevent real GCS  calls."""
    with patch(
        "merino.providers.suggest.finance.provider.Provider._fetch_manifest",
        new_callable=AsyncMock,
    ) as mock_fetch_manifest:
        yield mock_fetch_manifest


@pytest.mark.asyncio
async def test_init_providers() -> None:
    """Test for the `init_providers` method of the Merino suggest providers module."""
    await init_providers()

    providers, default_providers = get_providers()

    # a disabled provider should not be initialized
    assert providers.keys() == {
        provider.value for provider in ProviderType if provider.value not in DISABLED_PROVIDERS
    }

    assert {provider.name for provider in default_providers} == {
        provider.name for provider in providers.values() if provider.enabled_by_default
    }


@pytest.mark.asyncio
async def test_initialize_provider_records_otel_duration(mocker: MockerFixture) -> None:
    """Test provider initialization duration is recorded with a provider attribute."""
    provider = mocker.AsyncMock()
    histogram = mocker.patch("merino.providers.suggest._provider_initialize_duration")
    mocker.patch("merino.providers.suggest.timer", side_effect=[10.0, 10.125])

    await _initialize_provider("adm", provider)

    provider.initialize.assert_awaited_once_with()
    histogram.record.assert_called_once_with(125.0, {"provider": "adm"})


@pytest.mark.asyncio
async def test_initialize_provider_records_duration_on_error(mocker: MockerFixture) -> None:
    """Test failed initialization is timed and its error is propagated."""
    provider = mocker.AsyncMock()
    provider.initialize.side_effect = RuntimeError("initialization failed")
    histogram = mocker.patch("merino.providers.suggest._provider_initialize_duration")
    mocker.patch("merino.providers.suggest.timer", side_effect=[20.0, 20.25])

    with pytest.raises(RuntimeError, match="initialization failed"):
        await _initialize_provider("accuweather", provider)

    histogram.record.assert_called_once_with(250.0, {"provider": "accuweather"})


@pytest.mark.asyncio
async def test_init_providers_propagates_initialization_error(mocker: MockerFixture) -> None:
    """Test initialization errors propagate and both provider durations are recorded."""
    provider = mocker.AsyncMock()
    provider.initialize.side_effect = RuntimeError("initialization failed")
    mocker.patch("merino.providers.suggest.load_providers", return_value={"adm": provider})
    mocker.patch.dict("merino.providers.suggest.providers", {}, clear=True)
    histogram = mocker.patch("merino.providers.suggest._provider_initialize_duration")

    with pytest.raises(RuntimeError, match="initialization failed"):
        await init_providers()

    assert [call.args[1] for call in histogram.record.call_args_list] == [
        {"provider": "adm"},
        {"provider": "__ALL__"},
    ]


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
    mocker.patch.dict(
        settings.providers, values={"unknown-provider": DataDict({"type": "unknown-type"})}
    )

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

    records = filter_caplog(caplog.records, "merino.providers.suggest")

    assert len(records) == 2
    assert records[0].message == "Provider initialization completed"
    assert records[1].message == "Provider shutdown completed"

    providers = records[1].__dict__["providers"]

    assert set(providers) == {
        provider.value for provider in ProviderType if provider.value not in DISABLED_PROVIDERS
    }
