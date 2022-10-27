import pytest
from fastapi.testclient import TestClient
from pytest_mock import MockerFixture

from merino.config import settings
from merino.exceptions import InvalidProviderError
from merino.main import app
from merino.providers import ProviderType, get_providers, init_providers


@pytest.mark.asyncio
async def test_init_providers() -> None:
    """Test for the `init_providers` method of the Merino providers module."""

    await init_providers()

    providers, default_providers = get_providers()

    assert len(providers) == 4
    assert ProviderType.ADM in providers
    assert ProviderType.WIKI_FRUIT in providers
    assert ProviderType.TOP_PICKS in providers

    assert len(default_providers) == 3


@pytest.mark.asyncio
async def test_init_providers_unknown_provider_type(mocker: MockerFixture) -> None:
    """Test for the `init_providers` with an unknown provider."""

    mocker.patch.dict(settings.providers, values={"unknown-provider": {}})

    with pytest.raises(InvalidProviderError) as excinfo:
        await init_providers()

    assert str(excinfo.value) == "Unknown provider type: unknown-provider"


def test_unknow_providers_should_shutdown_app(mocker: MockerFixture) -> None:
    """Test Merino should shut down upon an unknown provider."""

    mocker.patch.dict(settings.providers, values={"unknown-provider": {}})

    with pytest.raises(InvalidProviderError) as excinfo:
        # This will run all the FastAPI startup event handlers.
        with TestClient(app):
            # should never make to here
            assert False

    assert str(excinfo.value) == "Unknown provider type: unknown-provider"
