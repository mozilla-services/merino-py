"""Unit tests for the Addon API provider backend"""

import json

import httpx
import pytest
from _pytest.logging import LogCaptureFixture
from httpx import AsyncClient, Request, Response
from pytest_mock import MockerFixture

from merino.providers.amo.addons_data import ADDON_DATA, SupportedAddon
from merino.providers.amo.backends.dynamic import (
    DynamicAmoBackend,
    DynamicAmoBackendException,
)
from merino.providers.amo.backends.protocol import Addon, AmoBackendError


@pytest.fixture(name="dynamic_backend")
def fixture_dynamic_backend() -> DynamicAmoBackend:
    """Create a AddonAPIBackend object for test."""
    return DynamicAmoBackend(api_url="https://addons.mozilla.org/api/v5/addons/addon")


def _patch_addons_api_calls(mocker: MockerFixture) -> None:
    """Set up the return request for the Mocked Addon API call."""
    sample_addon_resp = json.dumps(
        {
            "icon_url": "https://this.is.image",
            "ratings": {"average": 4.123, "count": 1234},
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
        for addon_key in SupportedAddon
    ]
    mocker.patch.object(AsyncClient, "get", side_effect=return_values)


@pytest.mark.asyncio
async def test_fetch_addons_succeed(mocker: MockerFixture, dynamic_backend: DynamicAmoBackend):
    """Test that fetch populates the Addons."""
    _patch_addons_api_calls(mocker)

    assert dynamic_backend.dynamic_data == {}
    await dynamic_backend.fetch_and_cache_addons_info()
    assert len(dynamic_backend.dynamic_data) == len(SupportedAddon)


@pytest.mark.asyncio
async def test_fetch_addons_skipped_api_failure(
    mocker: MockerFixture, caplog: LogCaptureFixture, dynamic_backend: DynamicAmoBackend
):
    """Test that fetch fails raises error when Addon requests fails before it
    returns a response.
    """
    mocker.patch.object(AsyncClient, "get", side_effect=httpx.TimeoutException("timedout!"))
    await dynamic_backend.fetch_and_cache_addons_info()

    # Ensure that all the messages are errors due to the timeout.
    for msg in caplog.messages:
        assert msg.startswith("Addons API failed request to fetch addon")


@pytest.mark.asyncio
async def test_fetch_addons_skipped_api_request_failure(
    mocker: MockerFixture, caplog: LogCaptureFixture, dynamic_backend: DynamicAmoBackend
):
    """Test that fetch fails raises error when Addon request fails."""
    sample_addon_resp = json.dumps(
        {
            "icon_url": "https://this.is.image",
            "ratings": {"average": 4.123, "count": 1234},
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
        for addon_key in SupportedAddon
    ]
    # Replace the first response with a 400
    return_values[0] = Response(
        status_code=400,
        content="Not Found",
        request=Request(
            method="GET",
            url="https://addons.mozilla.org/api/v5/addons/addon/video-downloadhelper",
        ),
    )

    mocker.patch.object(AsyncClient, "get", side_effect=return_values)

    await dynamic_backend.fetch_and_cache_addons_info()

    assert len(dynamic_backend.dynamic_data) == len(SupportedAddon) - 1
    assert len(caplog.messages) == 1
    assert caplog.messages[0].startswith("Addons API could not find key: video-downloadhelper")


@pytest.mark.asyncio
async def test_fetch_addons_skipped_bad_response(
    mocker: MockerFixture, caplog: LogCaptureFixture, dynamic_backend: DynamicAmoBackend
):
    """Test that fetch fails raises error when Addon request fails."""
    sample_addon_resp = json.dumps(
        {
            "icon_url": "https://this.is.image",
            "ratings": {"average": 4.123, "count": 1234},
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
        for addon_key in SupportedAddon
    ]
    return_values[0] = Response(
        status_code=200,
        content="bad response!! Not JSON",
        request=Request(
            method="GET",
            url="https://addons.mozilla.org/api/v5/addons/addon/video-downloadhelper",
        ),
    )
    mocker.patch.object(AsyncClient, "get", side_effect=return_values)

    await dynamic_backend.fetch_and_cache_addons_info()

    assert len(dynamic_backend.dynamic_data) == len(SupportedAddon) - 1
    assert len(caplog.messages) == 1
    assert (
        caplog.messages[0] == "Problem with Addons API formatting. "
        "Check that the API response structure hasn't changed."
    )


@pytest.mark.asyncio
async def test_fetch_addons_handled_task_group_exceptions(
    mocker: MockerFixture, dynamic_backend: DynamicAmoBackend
):
    """Test that `TaskGroup` exceptions are captured and propagated as `AmoBackendError`."""
    mocker.patch.object(dynamic_backend, "_fetch_addon", side_effect=Exception("mocked error"))

    with pytest.raises(AmoBackendError):
        await dynamic_backend.fetch_and_cache_addons_info()


@pytest.mark.asyncio
async def test_get_addon_request(mocker: MockerFixture, dynamic_backend: DynamicAmoBackend):
    """Test that we can get the Addons details."""
    _patch_addons_api_calls(mocker)
    await dynamic_backend.fetch_and_cache_addons_info()

    addons = await dynamic_backend.get_addon(SupportedAddon.VIDEO_DOWNLOADER)

    video_downloader = ADDON_DATA[SupportedAddon.VIDEO_DOWNLOADER]
    assert (
        Addon(
            name=video_downloader["name"],
            description=video_downloader["description"],
            url=video_downloader["url"],
            icon="https://this.is.image",
            rating="4.1",
            number_of_ratings=1234,
            guid=video_downloader["guid"],
        )
        == addons
    )


@pytest.mark.asyncio
async def test_get_addon_key_error(mocker: MockerFixture, dynamic_backend: DynamicAmoBackend):
    """Test that we raise the right error for Key Error."""
    _patch_addons_api_calls(mocker)
    await dynamic_backend.fetch_and_cache_addons_info()
    del dynamic_backend.dynamic_data[SupportedAddon.VIDEO_DOWNLOADER]

    with pytest.raises(DynamicAmoBackendException) as ex:
        await dynamic_backend.get_addon(SupportedAddon.VIDEO_DOWNLOADER)

    assert str(ex.value) == "Missing Addon in execution. Skip returning Addon."
