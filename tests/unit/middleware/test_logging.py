# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the middleware logging module."""

import logging

import pytest
from pytest import LogCaptureFixture
from pytest_mock import MockerFixture
from starlette.types import Receive, Scope, Send

from merino.utils.log_data_creators import SuggestLogDataModel
from merino.middleware.logging import LoggingMiddleware
from merino.configs import settings


async def app(scope: Scope, receive: Receive, send: Send) -> None:
    """Mock asgi app for testing."""
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [[b"content-type", b"application/json"]],
        }
    )


@pytest.mark.asyncio
async def test_logging_invalid_scope_type(
    mocker: MockerFixture,
    caplog: LogCaptureFixture,
    receive_mock: Receive,
    send_mock: Send,
) -> None:
    """Test that no logging action takes place for an unexpected Scope type."""
    caplog.set_level(logging.INFO)
    scope: Scope = {"type": "not-http"}
    logging_middleware: LoggingMiddleware = LoggingMiddleware(app)

    await logging_middleware(scope, receive_mock, send_mock)

    assert len(caplog.messages) == 0


@pytest.mark.asyncio
async def test_logging_toggle_suggest_request_logging(
    mocker: MockerFixture,
    caplog: LogCaptureFixture,
    receive_mock: Receive,
    send_mock: Send,
) -> None:
    """Test that no logging action takes place if suggest_request logging is disabled."""
    mocker.patch("merino.middleware.logging.LOG_SUGGEST_REQUEST", False)
    caplog.set_level(logging.INFO)
    scope: Scope = {"type": "http"}
    logging_middleware: LoggingMiddleware = LoggingMiddleware(app)

    await logging_middleware(scope, receive_mock, send_mock)

    assert len(caplog.messages) == 0


@pytest.mark.parametrize("provider", settings.logging.excluded_providers)
@pytest.mark.asyncio
async def test_no_logging_for_excluded_provider(
    caplog: LogCaptureFixture,
    receive_mock: Receive,
    send_mock: Send,
    provider: str,
) -> None:
    """Test that no logging action takes place for an excluded suggest provider."""
    caplog.set_level(logging.INFO)
    scope: Scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "https",
        "path": "api/v1/suggest",
        "query_string": f"q=&providers={provider}".encode(),
        "headers": [(b"host", b"www.example.org/"), (b"accept", b"application/json")],
        "merino_pii_detection": "non-pii",
    }
    logging_middleware: LoggingMiddleware = LoggingMiddleware(app)

    await logging_middleware(scope, receive_mock, send_mock)

    assert len(caplog.messages) == 0


@pytest.mark.asyncio
async def test_logging_for_included_provider(
    mocker: MockerFixture,
    caplog: LogCaptureFixture,
    receive_mock: Receive,
    send_mock: Send,
) -> None:
    """Test that logging action is taken for a successful suggest request."""
    mock_func = mocker.patch("merino.middleware.logging.create_suggest_log_data")
    mock_func.return_value = mocker.MagicMock(spec=SuggestLogDataModel)

    caplog.set_level(logging.INFO)
    scope: Scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "https",
        "path": "api/v1/suggest",
        "query_string": b"q=&providers=wikipedia",
        "headers": [(b"host", b"www.example.org/"), (b"accept", b"application/json")],
        "merino_pii_detection": "non-pii",
    }
    logging_middleware: LoggingMiddleware = LoggingMiddleware(app)

    await logging_middleware(scope, receive_mock, send_mock)

    assert len(caplog.messages) == 1
