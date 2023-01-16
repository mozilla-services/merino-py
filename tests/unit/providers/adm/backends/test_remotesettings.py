# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the Remote Settings backend module."""

from typing import Any

import httpx
import kinto_http
import pytest
from pytest_mock import MockerFixture

from merino.providers import RemoteSettingsBackend


@pytest.fixture(name="remote_settings_parameters")
def fixture_remote_settings_parameters() -> dict[str, str]:
    """Define default Remote Settings parameters for test."""
    return {
        "server": "test://test",
        "bucket": "main",
        "collection": "quicksuggest",
    }


@pytest.fixture(name="remote_settings")
def fixture_remote_settings(
    remote_settings_parameters: dict[str, str]
) -> RemoteSettingsBackend:
    """Create a RemoteSettingsBackend object for test."""
    return RemoteSettingsBackend(**remote_settings_parameters)


@pytest.fixture(name="remote_settings_server_info_response")
def fixture_remote_settings_server_info_response() -> dict[str, Any]:
    """Return response content for Remote Settings server_info() method."""
    return {
        "project_name": "Remote Settings PROD",
        "project_version": "15.0.0",
        "http_api_version": "1.22",
        "project_docs": "https://remote-settings.readthedocs.io",
        "url": "https://firefox.settings.services.mozilla.com/v1/",
        "settings": {
            "batch_max_requests": 25,
            "readonly": True,
            "explicit_permissions": False,
        },
        "capabilities": {
            "changes": {
                "description": (
                    "Track modifications of records in Kinto and store the collection "
                    "timestamps into a specific bucket and collection."
                ),
                "url": (
                    "http://kinto.readthedocs.io/en/latest/tutorials/"
                    "synchronisation.html#polling-for-remote-changes"
                ),
                "version": "30.1.1",
                "collections": [
                    "/buckets/blocklists",
                    "/buckets/blocklists-preview",
                    "/buckets/main",
                    "/buckets/main-preview",
                    "/buckets/security-state",
                    "/buckets/security-state-preview",
                ],
            },
            "attachments": {
                "description": "Add file attachments to records",
                "url": "https://github.com/Kinto/kinto-attachment/",
                "version": "6.3.1",
                "base_url": "https://firefox-settings-attachments.cdn.mozilla.net/",
            },
        },
    }


@pytest.mark.parametrize(
    "parameter",
    ["server", "collection", "bucket"],
)
def test_init_invalid_remote_settings_parameter_error(
    remote_settings_parameters: dict[str, str], parameter: str
) -> None:
    """Test that a ValueError is raised if initializing with empty Remote Settings
    values.
    """
    expected_error_value: str = (
        "The Remote Settings 'server', 'collection' or 'bucket' parameters are not "
        "specified"
    )
    remote_settings_parameters[parameter] = ""

    with pytest.raises(ValueError) as error:
        RemoteSettingsBackend(**remote_settings_parameters)

    assert str(error.value) == expected_error_value


@pytest.mark.asyncio
async def test_fetch_attachment_host(
    mocker: MockerFixture,
    remote_settings: RemoteSettingsBackend,
    remote_settings_server_info_response: dict[str, Any],
) -> None:
    """Test that the fetch_attachment_host method returns the proper server info."""
    expected_attachment_host: str = (
        "https://firefox-settings-attachments.cdn.mozilla.net/"
    )
    mocker.patch.object(
        kinto_http.AsyncClient,
        "server_info",
        return_value=remote_settings_server_info_response,
    )

    attachment_host: str = await remote_settings.fetch_attachment_host()

    assert attachment_host == expected_attachment_host


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "attachment_host",
    ["", "https://firefox-settings-attachments.cdn.mozilla.net/"],
    ids=["attachment_host_defined", "attachment_host_undefined"],
)
async def test_fetch_attachment(
    mocker: MockerFixture,
    remote_settings: RemoteSettingsBackend,
    remote_settings_server_info_response: dict[str, Any],
    attachment_host: str,
) -> None:
    """Test that the fetch_attachment method sends proper queries to Remote Settings."""
    attachment_uri: str = (
        "main-workspace/quicksuggest/6129d437-b3c1-48b5-b343-535e045d341a.json"
    )
    expected_uri: str = (
        f"https://firefox-settings-attachments.cdn.mozilla.net/{attachment_uri}"
    )
    remote_settings.attachment_host = attachment_host
    mocker.patch.object(
        kinto_http.AsyncClient,
        "server_info",
        return_value=remote_settings_server_info_response,
    )
    httpx_client_mock = mocker.patch.object(httpx.AsyncClient, "get")

    await remote_settings.fetch_attachment(attachment_uri)

    httpx_client_mock.assert_called_once_with(expected_uri)


@pytest.mark.parametrize(
    "attachment_host",
    ["", "https://firefox-settings-attachments.cdn.mozilla.net/"],
    ids=["attachment_host_defined", "attachment_host_undefined"],
)
def test_get_icon_url(
    remote_settings: RemoteSettingsBackend,
    attachment_host: str,
) -> None:
    """Test that the get_icon_url method returns a proper icon url."""
    icon_uri: str = "main-workspace/quicksuggest/05f7ba7a-f7cf-4288-a89f-8fad6970a3c9"
    expected_icon_url: str = f"{attachment_host}{icon_uri}"
    remote_settings.attachment_host = attachment_host

    icon_url: str = remote_settings.get_icon_url(icon_uri)

    assert icon_url == expected_icon_url
