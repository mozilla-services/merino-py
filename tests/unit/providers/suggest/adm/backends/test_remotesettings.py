# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the Remote Settings backend module."""

import json
from collections import defaultdict
from typing import Any
from urllib.parse import urljoin

import httpx
import kinto_http
import moz_merino_ext.amp
import pytest
from pytest import LogCaptureFixture
from httpx import HTTPError, Request, Response
from kinto_http import KintoException
from pytest_mock import MockerFixture

from merino.exceptions import BackendError
from merino.providers.suggest.adm.backends.protocol import SuggestionContent
from merino.providers.suggest.adm.backends.remotesettings import (
    KintoSuggestion,
    RemoteSettingsBackend,
    FormFactor,
)
from merino.utils.icon_processor import IconProcessor
from tests.types import FilterCaplogFixture


@pytest.fixture(name="rs_parameters")
def fixture_rs_parameters() -> dict[str, str]:
    """Define default Remote Settings parameters for test."""
    return {
        "server": "test://test",
        "bucket": "main",
        "collection": "quicksuggest",
    }


@pytest.fixture(name="mock_icon_processor")
def fixture_mock_icon_processor(mocker: MockerFixture) -> IconProcessor:
    """Create a mock IconProcessor for testing."""
    mock_processor: IconProcessor = mocker.create_autospec(IconProcessor, instance=True)

    async def mock_process(url: str, fallback_url: str | None = None) -> str:
        return url

    mock_processor.process_icon_url.side_effect = mock_process  # type: ignore
    return mock_processor


@pytest.fixture(name="rs_backend")
def fixture_rs_backend(
    rs_parameters: dict[str, str], mock_icon_processor: IconProcessor
) -> RemoteSettingsBackend:
    """Create a RemoteSettingsBackend object for test."""
    return RemoteSettingsBackend(
        server=rs_parameters["server"],
        collection=rs_parameters["collection"],
        bucket=rs_parameters["bucket"],
        icon_processor=mock_icon_processor,
    )


@pytest.fixture(name="rs_records")
def fixture_rs_records() -> list[dict[str, Any]]:
    """Return fake records data as generated by the Remote Settings get_records()
    method.
    """
    return [
        {
            "type": "amp",
            "country": "US",
            "form_factor": "desktop",
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
            "type": "amp",
            "country": "DE",
            "form_factor": "phone",
            "schema": 123,
            "attachment": {
                "hash": "abcd",
                "size": 1,
                "filename": "data-03.json",
                "location": "main-workspace/quicksuggest/attachmment-03.json",
                "mimetype": "application/octet-stream",
            },
            "id": "data-01",
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


@pytest.fixture(name="rs_server_info")
def fixture_rs_server_info() -> dict[str, Any]:
    """Return fake server information as generated by the Remote Settings server_info()
    method.
    """
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


@pytest.fixture(name="rs_attachment")
def fixture_rs_attachment() -> KintoSuggestion:
    """Return fake attachment data as generated by the Remote Settings endpoint."""
    return KintoSuggestion(
        id=2,
        advertiser="Example.org",
        impression_url="https://example.org/impression/mozilla",
        click_url="https://example.org/click/mozilla",
        full_keywords=[["firefox accounts", 3], ["mozilla firefox accounts", 4]],
        iab_category="5 - Education",
        icon="01",
        keywords=[
            "firefox",
            "firefox account",
            "firefox accounts",
            "mozilla",
            "mozilla firefox",
            "mozilla firefox account",
            "mozilla firefox accounts",
        ],
        title="Mozilla Firefox Accounts",
        url="https://example.org/target/mozfirefoxaccounts",
    )


@pytest.fixture(name="rs_attachment_response")
def fixture_rs_attachment_response(rs_attachment: KintoSuggestion) -> httpx.Response:
    """Return response content for a Remote Settings attachment."""
    return httpx.Response(
        status_code=200,
        json=[dict(rs_attachment)],
        request=httpx.Request(
            method="GET",
            url=(
                "attachment-host/main-workspace/quicksuggest/"
                "6129d437-b3c1-48b5-b343-535e045d341a.json"
            ),
        ),
    )


@pytest.fixture(name="rs_wiki_attachment")
def fixture_rs_wiki_attachment() -> KintoSuggestion:
    """Return fake attachment data containing Wiki-adm suggestion as generated
    by the Remote Settings endpoint.
    """
    return KintoSuggestion(
        id=2,
        advertiser="Wikipedia",
        impression_url="https://wikipedia.org/impression/mozilla",
        click_url="https://wikipedia.org/en/Mozilla",
        full_keywords=[["firefox accounts", 3], ["mozilla firefox accounts", 4]],
        iab_category="5 - Education",
        icon="01",
        keywords=[
            "firefox",
            "firefox account",
            "firefox accounts",
            "mozilla",
            "mozilla firefox",
            "mozilla firefox account",
            "mozilla firefox accounts",
        ],
        title="Mozilla Wikipedia Accounts",
        url="https://wikipedia.org/en/Mozilla",
    )


@pytest.fixture(name="rs_wiki_attachment_response")
def fixture_rs_wiki_attachment_response(
    rs_wiki_attachment: KintoSuggestion,
) -> httpx.Response:
    """Return response content for a Remote Settings attachment."""
    return httpx.Response(
        status_code=200,
        json=[dict(rs_wiki_attachment)],
        request=httpx.Request(
            method="GET",
            url="",
        ),
    )


@pytest.mark.parametrize(
    "parameter",
    ["server", "collection", "bucket"],
)
def test_init_invalid_remote_settings_parameter_error(
    rs_parameters: dict[str, str], parameter: str, mock_icon_processor: IconProcessor
) -> None:
    """Test that a ValueError is raised if initializing with empty Remote Settings
    values.
    """
    expected_error_value: str = (
        "The Remote Settings 'server', 'collection' or 'bucket' parameters are not " "specified"
    )
    rs_parameters[parameter] = ""

    with pytest.raises(ValueError) as error:
        RemoteSettingsBackend(
            server=rs_parameters.get("server"),
            collection=rs_parameters.get("collection"),
            bucket=rs_parameters.get("bucket"),
            icon_processor=mock_icon_processor,
        )

    assert str(error.value) == expected_error_value


@pytest.mark.asyncio
async def test_fetch(
    mocker: MockerFixture,
    rs_backend: RemoteSettingsBackend,
    rs_records: list[dict[str, Any]],
    rs_server_info: dict[str, Any],
    rs_attachment_response: httpx.Response,
) -> None:
    """Test that the fetch method returns the proper suggestion content."""
    de_phone_attachment = KintoSuggestion(
        id=3,
        advertiser="de.Example.org",
        impression_url="https://de.example.org/impression/mozilla",
        click_url="https://de.example.org/click/mozilla",
        full_keywords=[
            ["firefox accounts de", 3],
        ],
        iab_category="5 - Education",
        icon="01",
        keywords=[
            "firefox",
            "firefox account",
            "firefox accounts de",
        ],
        title="Mozilla Firefox Accounts",
        url="https://de.example.org/target/mozfirefoxaccounts",
    )
    de_phone_attachment_response = httpx.Response(
        status_code=200,
        json=[dict(de_phone_attachment)],
        request=httpx.Request(
            method="GET",
            url=(
                "attachment-host/main-workspace/quicksuggest/"
                "6129d437-b3c1-48b5-b343-535e045d341a.json"
            ),
        ),
    )
    mocker.patch.object(kinto_http.AsyncClient, "get_records", return_value=rs_records)
    mocker.patch.object(kinto_http.AsyncClient, "server_info", return_value=rs_server_info)
    mocker.patch.object(
        httpx.AsyncClient,
        "get",
        side_effect=[rs_attachment_response, de_phone_attachment_response],
    )

    suggestion_content: SuggestionContent = await rs_backend.fetch()

    assert suggestion_content.index_manager.stats(f"DE/({FormFactor.PHONE.value},)") == {
        "advertisers_count": 1,
        "keyword_index_size": 3,
        "url_templates_count": 1,
        "icons_count": 1,
        "suggestions_count": 1,
    }


@pytest.mark.asyncio
async def test_fetch_with_index_build_fail(
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
    mocker: MockerFixture,
    rs_backend: RemoteSettingsBackend,
    rs_records: list[dict[str, Any]],
    rs_server_info: dict[str, Any],
    rs_attachment_response: httpx.Response,
) -> None:
    """Test logging when building the index fails."""
    mocker.patch.object(kinto_http.AsyncClient, "get_records", return_value=rs_records)
    mocker.patch.object(kinto_http.AsyncClient, "server_info", return_value=rs_server_info)
    mocker.patch.object(
        httpx.AsyncClient,
        "get",
        return_value=rs_attachment_response,
    )
    mocker.patch.object(
        moz_merino_ext.amp.AmpIndexManager, "build", side_effect=Exception("Build Index Error")
    )

    _ = await rs_backend.fetch()
    records = filter_caplog(caplog.records, "merino.providers.suggest.adm.backends.remotesettings")
    assert len(records) == 2
    for record in records:
        assert record.__dict__["error message"] == "Build Index Error"


@pytest.mark.asyncio
async def test_fetch_skip(
    mocker: MockerFixture,
    rs_backend: RemoteSettingsBackend,
    rs_records: list[dict[str, Any]],
    rs_server_info: dict[str, Any],
    rs_attachment_response: httpx.Response,
) -> None:
    """Test that the fetch method should skip records processing if the records are up to date."""
    mocker.patch.object(kinto_http.AsyncClient, "get_records", return_value=rs_records)
    mocker.patch.object(kinto_http.AsyncClient, "server_info", return_value=rs_server_info)
    mocker.patch.object(httpx.AsyncClient, "get", return_value=rs_attachment_response)

    suggestion_content_1st: SuggestionContent = await rs_backend.fetch()
    assert set(suggestion_content_1st.index_manager.list()) == {"US/(0,)", "DE/(1,)"}

    # clear index
    suggestion_content_1st.index_manager.delete("US/(0,)")
    suggestion_content_1st.index_manager.delete("DE/(1,)")
    assert suggestion_content_1st.index_manager.list() == []

    # call it again, it should be short-circuited as the record is already processed and up to date.
    spy = mocker.spy(rs_backend, "get_suggestions")
    suggestion_content_2nd: SuggestionContent = await rs_backend.fetch()

    spy.assert_not_called()

    # index should still be empty
    assert suggestion_content_2nd.index_manager.list() == []

    # update the "last_modified" field, fetch should proceed as usual.
    rs_records[0]["last_modified"] = rs_records[0]["last_modified"] + 1

    suggestion_content_3rd: SuggestionContent = await rs_backend.fetch()

    spy.assert_called_once()

    # index should be rebuilt
    assert set(suggestion_content_3rd.index_manager.list()) == {"US/(0,)", "DE/(1,)"}


@pytest.mark.asyncio
async def test_filter_amp_records(
    rs_records: list[dict[str, Any]],
    rs_backend: RemoteSettingsBackend,
) -> None:
    """Test that the filter_records method returns the proper records."""
    suggestion_content = rs_backend.filter_records("amp", rs_records)

    assert suggestion_content == [
        {
            "type": "amp",
            "country": "US",
            "form_factor": "desktop",
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
            "type": "amp",
            "country": "DE",
            "form_factor": "phone",
            "schema": 123,
            "attachment": {
                "hash": "abcd",
                "size": 1,
                "filename": "data-03.json",
                "location": "main-workspace/quicksuggest/attachmment-03.json",
                "mimetype": "application/octet-stream",
            },
            "id": "data-01",
            "last_modified": 123,
        },
    ]


@pytest.mark.asyncio
async def test_get_records_backend_error(
    mocker: MockerFixture,
    rs_backend: RemoteSettingsBackend,
) -> None:
    """Test that the method raises an appropriate exception in the event of an
    error while getting the records.
    """
    expected_error_value: str = "Failed to get records"
    mocker.patch.object(
        kinto_http.AsyncClient,
        "get_records",
        side_effect=KintoException("403 - Forbidden"),
    )

    with pytest.raises(BackendError) as error:
        await rs_backend.get_records()

    assert str(error.value) == expected_error_value


@pytest.mark.asyncio
async def test_get_attachment_host(
    mocker: MockerFixture,
    rs_backend: RemoteSettingsBackend,
    rs_server_info: dict[str, Any],
) -> None:
    """Test that the method returns the proper attachment host."""
    expected_attachment_host: str = "attachment-host/"
    mocker.patch.object(kinto_http.AsyncClient, "server_info", return_value=rs_server_info)

    attachment_host: str = await rs_backend.get_attachment_host()

    assert attachment_host == expected_attachment_host


@pytest.mark.asyncio
async def test_get_attachment_host_backend_error(
    mocker: MockerFixture,
    rs_backend: RemoteSettingsBackend,
) -> None:
    """Test that the method raises an appropriate exception in the event of an
    error while getting the attachment host.
    """
    expected_error_value: str = "Failed to get server information"
    mocker.patch.object(
        kinto_http.AsyncClient,
        "server_info",
        side_effect=KintoException("403 - Forbidden"),
    )

    with pytest.raises(BackendError) as error:
        await rs_backend.get_attachment_host()

    assert str(error.value) == expected_error_value


@pytest.mark.asyncio
async def test_get_suggestions(
    mocker: MockerFixture,
    rs_backend: RemoteSettingsBackend,
    rs_records: list[dict[str, Any]],
    rs_attachment: KintoSuggestion,
    rs_attachment_response: httpx.Response,
) -> None:
    """Test that the method returns the proper suggestion information."""
    attachment_host: str = "attachment-host/"
    mocker.patch.object(httpx.AsyncClient, "get", return_value=rs_attachment_response)

    suggestions: defaultdict[str, defaultdict[tuple[int], str]] = await rs_backend.get_suggestions(
        attachment_host, rs_backend.filter_records("amp", rs_records)
    )
    expected_suggestion_info = [
        ("US", (FormFactor.DESKTOP.value,)),
        ("DE", (FormFactor.PHONE.value,)),
    ]
    expected_suggestion_data_str = json.dumps(
        [
            {
                "id": 2,
                "advertiser": "Example.org",
                "click_url": "https://example.org/click/mozilla",
                "full_keywords": [["firefox accounts", 3], ["mozilla firefox accounts", 4]],
                "iab_category": "5 - Education",
                "icon": "01",
                "impression_url": "https://example.org/impression/mozilla",
                "keywords": [
                    "firefox",
                    "firefox account",
                    "firefox accounts",
                    "mozilla",
                    "mozilla firefox",
                    "mozilla firefox account",
                    "mozilla firefox accounts",
                ],
                "title": "Mozilla Firefox Accounts",
                "url": "https://example.org/target/mozfirefoxaccounts",
            }
        ]
    )
    for country, segment in expected_suggestion_info:
        assert country in suggestions.keys()
        assert list(suggestions[country].keys()) == [segment]
        assert suggestions[country][segment] == expected_suggestion_data_str


@pytest.mark.asyncio
async def test_get_suggestions_backend_error(
    mocker: MockerFixture,
    rs_backend: RemoteSettingsBackend,
    rs_records: list[dict[str, Any]],
) -> None:
    """Test that the method raises an appropriate exception in the event of an
    error while getting the suggestion information.
    """
    expected_error_value: str = "(RemoteSettingsError('Failed to get attachment'), RemoteSettingsError('Failed to get attachment'))"
    attachment_host: str = "attachment-host/"
    mocker.patch.object(
        httpx.AsyncClient,
        "get",
        side_effect=HTTPError("Invalid Request - Get Attachment"),
    )

    with pytest.raises(BackendError) as error:
        await rs_backend.get_suggestions(
            attachment_host, rs_backend.filter_records("amp", rs_records)
        )

    assert str(error.value) == expected_error_value


@pytest.mark.asyncio
async def test_get_attachment(
    mocker: MockerFixture,
    rs_backend: RemoteSettingsBackend,
    rs_attachment: KintoSuggestion,
    rs_attachment_response: httpx.Response,
) -> None:
    """Test that the method returns the proper attachment information."""
    expected_attachment: str = json.dumps([dict(rs_attachment)])
    url: str = urljoin(
        base="attachment-host",
        url="main-workspace/quicksuggest/6129d437-b3c1-48b5-b343-535e045d341a.json",
    )
    mocker.patch.object(httpx.AsyncClient, "get", return_value=rs_attachment_response)

    attachment: str = await rs_backend.get_attachment_raw(url)

    assert attachment == expected_attachment


@pytest.mark.asyncio
async def test_get_attachment_backend_error(
    mocker: MockerFixture, rs_backend: RemoteSettingsBackend
) -> None:
    """Test that the method raises an appropriate exception in the event of an
    error while getting the attachment information.
    """
    expected_error_value: str = "Failed to get attachment"
    url: str = urljoin(
        base="attachment-host",
        url="main-workspace/quicksuggest/6129d437-b3c1-48b5-b343-535e045d341a.json",
    )
    mocker.patch.object(
        httpx.AsyncClient,
        "get",
        return_value=Response(
            status_code=403,
            text=(
                f"Client error '403 Forbidden' for url '{url}' "
                f"For more information check: https://httpstatuses.com/403"
            ),
            request=Request(method="GET", url=url),
        ),
    )

    with pytest.raises(BackendError) as error:
        await rs_backend.get_attachment_raw(url)

    assert str(error.value) == expected_error_value
