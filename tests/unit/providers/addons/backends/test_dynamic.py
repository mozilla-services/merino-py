"""Unit tests for the Addon API provider backend"""
import json

import pytest
from httpx import AsyncClient, Response, Request

from pytest_mock import MockerFixture

from merino.providers.addons.addons_data import ADDON_DATA, SUPPORTED_ADDONS_KEYS
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


def _patch_addons_api_calls(mocker: MockerFixture):
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
        for addon_key in SUPPORTED_ADDONS_KEYS
    ]
    mocker.patch.object(AsyncClient, "get", side_effect=return_values)


@pytest.mark.asyncio
async def test_initialize_addons_succeed(
    mocker: MockerFixture, dynamic_backend: DynamicAddonsBackend
):
    _patch_addons_api_calls(mocker)

    assert dynamic_backend.dynamic_data == {}
    await dynamic_backend.initialize_addons()
    assert len(dynamic_backend.dynamic_data) == len(SUPPORTED_ADDONS_KEYS)


@pytest.mark.asyncio
async def test_initialize_addons_failed(
    mocker: MockerFixture, dynamic_backend: DynamicAddonsBackend
):
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


@pytest.mark.asyncio
async def test_get_addon_request(
    mocker: MockerFixture, dynamic_backend: DynamicAddonsBackend
):
    """Test that we can get the Addons details via the Addon API."""
    _patch_addons_api_calls(mocker)
    await dynamic_backend.initialize_addons()

    addons = await dynamic_backend.get_addon("video-downloadhelper")

    video_downloader = ADDON_DATA["video-downloadhelper"]
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


@pytest.mark.asyncio
async def test_get_addon_bad_addon_key(dynamic_backend: DynamicAddonsBackend):
    """Test that a bad key raises and error."""
    with pytest.raises(KeyError) as ex:
        await dynamic_backend.get_addon("bad_key")

    assert str(ex.value) == "'bad_key'"
