# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the __init__ widget provider module."""

from unittest.mock import patch

import pytest

import merino.providers.widgets as widgets
from merino.providers.widgets import get_wrexham_provider, init_providers, shutdown_providers
from merino.providers.widgets.wrexham.provider import WrexhamProvider


@pytest.mark.asyncio
async def test_init_providers_uses_mock_data_setting() -> None:
    """Initializes the Wrexham provider with the configured mock data flag."""
    with patch("merino.providers.widgets._wrexham_mock_data_enabled", False):
        await init_providers()

    wrexham_provider = widgets._wrexham_provider

    assert isinstance(wrexham_provider, WrexhamProvider)
    assert wrexham_provider.mock_data_enabled is False


@pytest.mark.asyncio
async def test_get_wrexham_provider_initialized() -> None:
    """Returns the provider instance after init_providers is called."""
    await init_providers()

    assert isinstance(get_wrexham_provider(), WrexhamProvider)


def test_get_wrexham_provider_not_initialized() -> None:
    """Raises ValueError when the provider hasn't been initialized."""
    with patch("merino.providers.widgets._wrexham_provider", None):
        with pytest.raises(ValueError, match="Wrexham widget provider has not been initialized."):
            get_wrexham_provider()


@pytest.mark.asyncio
async def test_shutdown_providers_shuts_down_and_resets() -> None:
    """Shuts down the Wrexham provider and clears module state."""
    await init_providers()
    provider = widgets._wrexham_provider
    assert provider is not None

    with patch.object(provider, "shutdown") as shutdown:
        await shutdown_providers()

    shutdown.assert_awaited_once()
    assert widgets._wrexham_provider is None
    with pytest.raises(ValueError, match="Wrexham widget provider has not been initialized."):
        get_wrexham_provider()


@pytest.mark.asyncio
async def test_shutdown_providers_when_not_initialized() -> None:
    """Does nothing when no provider has been initialized."""
    with patch("merino.providers.widgets._wrexham_provider", None):
        await shutdown_providers()
