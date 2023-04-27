"""Unit tests for the Addon API provider backend"""
import json

import pytest
from httpx import AsyncClient, Request, Response
from pytest_mock import MockerFixture

from merino.providers.addons.addons_data import ADDON_DATA, SupportedAddons
from merino.providers.addons.backends.dynamic import (
    DynamicAddonsBackend,
    DynamicAddonsBackendException,
)
from merino.providers.addons.backends.protocol import Addon


@pytest.fixture(name="dynamic_backend")
def fixture_dynamic_backend() -> DynamicAddonsBackend:
    """Create a AddonAPIBackend object for test."""
    return DynamicAddonsBackend(
        api_url="https://addons.mozilla.org/api/v5/addons/addon"
    )


def _patch_addons_api_calls(mocker: MockerFixture) -> None:
    """Set up the return request for the Mocked Addon API call."""
    sample_addon_resp = json.dumps(
        {
            "icon_url": "https://this.is.image",
            "ratings": {
                "average": 4.123,
            },
        }
    ).encode("utf-8")
    return_values: list[Response] = [
        Response(
            status_code=200,
            content=sample_addon_resp,
            request=Request(
                method="GET",
                url=f"https://addons.mozilla.org/api/v5/addons/addon/{addon_key}",
            ),
        )
        for addon_key in SupportedAddons
    ]
    mocker.patch.object(AsyncClient, "get", side_effect=return_values)


@pytest.mark.asyncio
async def test_initialize_addons_succeed(
    mocker: MockerFixture, dynamic_backend: DynamicAddonsBackend
):
    """Test that initialize populates the Addons."""
    _patch_addons_api_calls(mocker)

    assert dynamic_backend.dynamic_data == {}
    await dynamic_backend.initialize_addons()
    assert len(dynamic_backend.dynamic_data) == len(SupportedAddons)


@pytest.mark.asyncio
async def test_initialize_addons_failed(
    mocker: MockerFixture, dynamic_backend: DynamicAddonsBackend
):
    """Test that initialize fails raises error when Addon request fails."""
    return_values: list[Response] = [
        Response(
            status_code=400,
            content="Not Found",
            request=Request(
                method="GET",
                url="https://addons.mozilla.org/api/v5/addons/addon/video-downloadhelper",
            ),
        )
    ]
    mocker.patch.object(AsyncClient, "get", side_effect=return_values)

    with pytest.raises(DynamicAddonsBackendException) as ex:
        await dynamic_backend.initialize_addons()

    assert str(ex.value).startswith("Addons API could not find key: ")


@pytest.mark.asyncio
async def test_get_addon_request(
    mocker: MockerFixture, dynamic_backend: DynamicAddonsBackend
):
    """Test that we can get the Addons details via the Addon API."""
    _patch_addons_api_calls(mocker)
    await dynamic_backend.initialize_addons()

    addons = await dynamic_backend.get_addon(SupportedAddons.VIDEO_DOWNLOADER)

    video_downloader = ADDON_DATA[SupportedAddons.VIDEO_DOWNLOADER]
    assert (
        Addon(
            name=video_downloader["name"],
            description=video_downloader["description"],
            url=video_downloader["url"],
            icon="https://this.is.image",
            rating=4.123,
        )
        == addons
    )
