# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the Remote Settings backend module."""
import json
from typing import Any

import httpx
import kinto_http
import pytest
from pytest_mock import MockerFixture

from merino.providers import RemoteSettingsBackend
from merino.providers.adm.backends.protocol import Content


@pytest.fixture(name="rs_parameters")
def fixture_rs_parameters() -> dict[str, str]:
    """Define default Remote Settings parameters for test."""
    return {
        "server": "test://test",
        "bucket": "main",
        "collection": "quicksuggest",
    }


@pytest.fixture(name="rs_backend")
def fixture_rs_backend(rs_parameters: dict[str, str]) -> RemoteSettingsBackend:
    """Create a RemoteSettingsBackend object for test."""
    return RemoteSettingsBackend(**rs_parameters)


@pytest.fixture(name="rs_get_records_response")
def fixture_rs_get_records_response() -> list[dict[str, Any]]:
    """Return response content for Remote Settings get_records() method."""
    return [
        {
            "type": "data",
            "schema": 123,
            "attachment": {
                "hash": "abcd",
                "size": 1,
                "filename": "data-01.json",
                "location": "main-workspace/quicksuggest/attachmment-01.json",
                "mimetype": "application/octet-stream",
            },
            "id": "data-01",
            "last_modified": 123,
        },
        {
            "type": "offline-expansion-data",
            "schema": 111,
            "attachment": {
                "hash": "efgh",
                "size": 1,
                "filename": "offline-expansion-data-01.json",
                "location": "main-workspace/quicksuggest/attachment-02.json",
                "mimetype": "application/octet-stream",
            },
            "id": "offline-expansion-data-01",
            "last_modified": 123,
        },
        {
            "type": "icon",
            "schema": 456,
            "attachment": {
                "hash": "efghabcasd",
                "size": 1,
                "filename": "icon-01",
                "location": "main-workspace/quicksuggest/icon-01",
                "mimetype": "application/octet-stream",
            },
            "content_type": "image/png",
            "id": "icon-01",
            "last_modified": 123,
        },
    ]


@pytest.fixture(name="rs_server_info_response")
def fixture_rs_server_info_response() -> dict[str, Any]:
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
                "base_url": "attachment-host/",
            },
        },
    }


@pytest.fixture(name="rs_attachment_response")
def fixture_rs_attachment_response() -> httpx.Response:
    """Return response content for a Remote Settings attachment."""
    attachment: dict[str, Any] = {
        "id": 2,
        "url": "https://example.org/target/mozfirefoxaccounts",
        "click_url": "https://example.org/click/mozilla",
        "iab_category": "5 - Education",
        "icon": "01",
        "advertiser": "Example.org",
        "title": "Mozilla Firefox Accounts",
        "keywords": [
            "firefox",
            "firefox account",
            "firefox accounts",
            "mozilla",
            "mozilla firefox",
            "mozilla firefox account",
            "mozilla firefox accounts",
        ],
        "full_keywords": [
            ("firefox accounts", 3),
            ("mozilla firefox accounts", 4),
        ],
    }
    return httpx.Response(200, text=json.dumps([attachment]))


@pytest.mark.parametrize(
    "parameter",
    ["server", "collection", "bucket"],
)
def test_init_invalid_remote_settings_parameter_error(
    rs_parameters: dict[str, str], parameter: str
) -> None:
    """Test that a ValueError is raised if initializing with empty Remote Settings
    values.
    """
    expected_error_value: str = (
        "The Remote Settings 'server', 'collection' or 'bucket' parameters are not "
        "specified"
    )
    rs_parameters[parameter] = ""

    with pytest.raises(ValueError) as error:
        RemoteSettingsBackend(**rs_parameters)

    assert str(error.value) == expected_error_value


@pytest.mark.asyncio
async def test_fetch_attachment_host(
    mocker: MockerFixture,
    rs_backend: RemoteSettingsBackend,
    rs_server_info_response: dict[str, Any],
) -> None:
    """Test that the fetch_attachment_host method returns the proper server info."""
    expected_attachment_host: str = "attachment-host/"
    mocker.patch.object(
        kinto_http.AsyncClient,
        "server_info",
        return_value=rs_server_info_response,
    )

    attachment_host: str = await rs_backend.fetch_attachment_host()

    assert attachment_host == expected_attachment_host


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "attachment_host",
    ["", "attachment-host/"],
    ids=["attachment_host_defined", "attachment_host_undefined"],
)
async def test_fetch_attachment(
    mocker: MockerFixture,
    rs_backend: RemoteSettingsBackend,
    rs_server_info_response: dict[str, Any],
    attachment_host: str,
) -> None:
    """Test that the fetch_attachment method sends proper queries to Remote Settings."""
    attachment_uri: str = (
        "main-workspace/quicksuggest/6129d437-b3c1-48b5-b343-535e045d341a.json"
    )
    expected_uri: str = f"attachment-host/{attachment_uri}"
    rs_backend.attachment_host = attachment_host
    mocker.patch.object(
        kinto_http.AsyncClient,
        "server_info",
        return_value=rs_server_info_response,
    )
    httpx_client_mock = mocker.patch.object(httpx.AsyncClient, "get")

    await rs_backend.fetch_attachment(attachment_uri)

    httpx_client_mock.assert_called_once_with(expected_uri)


@pytest.mark.parametrize(
    "attachment_host",
    ["", "attachment-host/"],
    ids=["attachment_host_defined", "attachment_host_undefined"],
)
def test_get_icon_url(rs_backend: RemoteSettingsBackend, attachment_host: str) -> None:
    """Test that the get_icon_url method returns a proper icon url."""
    icon_uri: str = "main-workspace/quicksuggest/05f7ba7a-f7cf-4288-a89f-8fad6970a3c9"
    expected_icon_url: str = f"{attachment_host}{icon_uri}"
    rs_backend.attachment_host = attachment_host

    icon_url: str = rs_backend.get_icon_url(icon_uri)

    assert icon_url == expected_icon_url


@pytest.mark.asyncio
async def test_fetch(
    mocker: MockerFixture,
    rs_backend: RemoteSettingsBackend,
    rs_get_records_response: list[dict[str, Any]],
    rs_server_info_response: dict[str, Any],
    rs_attachment_response: httpx.Response,
    adm_suggestion_content: Content,
) -> None:
    """Test that the fetch method returns the proper suggestion content."""
    rs_backend.attachment_host = "attachment-host/"
    mocker.patch.object(
        kinto_http.AsyncClient, "get_records", return_value=rs_get_records_response
    )
    mocker.patch.object(
        kinto_http.AsyncClient, "server_info", return_value=rs_server_info_response
    )
    mocker.patch.object(httpx.AsyncClient, "get", return_value=rs_attachment_response)

    content: Content = await rs_backend.fetch()

    assert content == adm_suggestion_content
