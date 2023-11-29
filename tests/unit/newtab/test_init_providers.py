"""Tests for the initialization and tear down functions for the New Tab providers."""
import logging
from typing import Any

import pytest
from _pytest.logging import LogCaptureFixture
from pytest_mock import MockerFixture

import merino.newtab
from merino.config import settings
from merino.newtab import get_upday_provider, init_providers, shutdown_providers


@pytest.fixture(name="upday_provider", autouse=True)
def fixture_upday_provider() -> Any:
    """Fixture for the upday provider. Ensure that we reset it on every run."""
    merino.newtab.upday_provider = None
    yield
    merino.newtab.upday_provider = None


@pytest.mark.asyncio
async def test_init_provider(caplog: LogCaptureFixture) -> None:
    """Test that we can create a provider with the given"""
    caplog.set_level(logging.INFO)

    assert get_upday_provider() is None

    with settings.using_env("testing"):
        await init_providers()

    assert get_upday_provider() is not None

    assert len(caplog.records) == 1
    assert caplog.messages[0] == "Initialized Upday Provider"


@pytest.mark.asyncio
async def test_skip_init_provider(caplog: LogCaptureFixture) -> None:
    """Test that we can skip initializing a provider if there is no password."""
    caplog.set_level(logging.INFO)

    assert get_upday_provider() is None

    with settings.using_env("production"):
        await init_providers()

    assert get_upday_provider() is None

    assert len(caplog.records) == 1
    assert caplog.messages[0] == "Skip initializing Upday Provider"


@pytest.mark.asyncio
async def test_shutdown_providers(mocker: MockerFixture) -> None:
    """Ensures that the shutdown_providers method closes down the providers."""
    upday_mock = mocker.AsyncMock()
    merino.newtab.upday_provider = upday_mock

    await shutdown_providers()

    upday_mock.shutdown.assert_called()


@pytest.mark.asyncio
async def test_shutdown_providers_no_providers() -> None:
    """Ensures that the shutdown provider does not cause a problem."""
    await shutdown_providers()
    assert get_upday_provider() is None
