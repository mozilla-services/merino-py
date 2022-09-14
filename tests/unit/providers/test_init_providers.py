import asyncio

import pytest

from merino.providers import ProviderType, get_providers, init_providers


@pytest.mark.asyncio
async def test_init_providers(mocker) -> None:
    """Test for the `init_providers` method of the Merino providers module."""

    future = asyncio.Future()
    # Don't fetch Remote Settings for tests
    mocker.patch("merino.providers.adm.Provider._fetch", return_value=future)

    await init_providers()

    providers, default_providers = get_providers()

    assert len(providers) == 2
    assert ProviderType.ADM in providers
    assert ProviderType.WIKI_FRUIT in providers

    assert len(default_providers) == 2
