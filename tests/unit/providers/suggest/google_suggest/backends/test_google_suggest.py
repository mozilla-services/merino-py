# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the Google Suggest backend."""

import json

import pytest

from unittest.mock import AsyncMock
from httpx import AsyncClient, Request, Response
from pytest_mock import MockerFixture
from typing import Any, cast
from merino.exceptions import BackendError
from merino.providers.suggest.google_suggest.backends.google_suggest import GoogleSuggestBackend
from merino.providers.suggest.google_suggest.backends.protocol import (
    GoogleSuggestResponse,
    SuggestRequest,
)
from tests.types import FilterCaplogFixture
from pytest import LogCaptureFixture
from merino.configs import settings


@pytest.fixture(name="suggest_request")
def fixture_suggest_request() -> SuggestRequest:
    """Create a fixture for the test suggest request."""
    return SuggestRequest(query="test", params="client%30firefox%26q%30test")


@pytest.fixture(name="backend")
def fixture_backend(
    mocker: MockerFixture,
    statsd_mock: Any,
) -> GoogleSuggestBackend:
    """Create a Polygon backend module object."""
    return GoogleSuggestBackend(
        metrics_client=statsd_mock,
        url_suggest_path=settings.google_suggest.url_suggest_path,
        http_client=mocker.AsyncMock(spec=AsyncClient),
    )


@pytest.mark.asyncio
async def test_fetch_google_success(
    backend: GoogleSuggestBackend,
    suggest_request: SuggestRequest,
    google_suggest_response: GoogleSuggestResponse,
) -> None:
    """Test fetch suggestions from the Google Suggest endpoint - success."""
    cast(AsyncMock, backend.http_client).get.return_value = Response(
        status_code=200,
        content=json.dumps(google_suggest_response),
        request=Request(method="GET", url=""),
    )

    suggestions = await backend.fetch(suggest_request)

    assert suggestions == google_suggest_response

    cast(AsyncMock, backend.metrics_client).timeit.assert_called_once_with(
        "google_suggest.request.duration"
    )


@pytest.mark.asyncio
async def test_fetch_google_error(
    backend: GoogleSuggestBackend,
    suggest_request: SuggestRequest,
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
) -> None:
    """Test fetch suggestions from the Google Suggest endpoint - success."""
    cast(AsyncMock, backend.http_client).get.return_value = Response(
        status_code=500,
        content=None,
        request=Request(method="GET", url=""),
    )

    with pytest.raises(BackendError):
        _ = await backend.fetch(suggest_request)

    cast(AsyncMock, backend.metrics_client).increment.assert_called_once_with(
        "google_suggest.request.failure", tags={"status_code": 500}
    )

    records = filter_caplog(
        caplog.records, "merino.providers.suggest.google_suggest.backends.google_suggest"
    )

    assert len(caplog.records) == 1

    assert records[0].message.startswith("Google Suggest request error")
