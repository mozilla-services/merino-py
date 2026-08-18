# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the middleware logging module."""

import logging
from datetime import UTC, datetime, timedelta

import pytest
from pytest import LogCaptureFixture
from pytest_mock import MockerFixture
from starlette.types import Receive, Scope, Send

from merino.middleware.logging import LoggingMiddleware
from merino.utils.featureflags import FeatureFlags
from merino_common.models.suggest_logging import (
    MozlogDataModel,
    SuggestLogDataModel,
    SuggestRequestParams,
)
from merino_common.utils.async_batch_queue import QueueFullException
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


def _suggest_scope() -> Scope:
    """Return a scope for a qualifying (non-excluded, non-PII) suggest request."""
    return {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "https",
        "path": "/api/v1/suggest",
        "query_string": b"q=&providers=wikipedia",
        "headers": [(b"host", b"www.example.org/"), (b"accept", b"application/json")],
        "merino_pii_detection": "non-pii",
    }


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
        "path": "/api/v1/suggest",
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
        "path": "/api/v1/suggest",
        "query_string": b"q=&providers=wikipedia",
        "headers": [(b"host", b"www.example.org/"), (b"accept", b"application/json")],
        "merino_pii_detection": "non-pii",
    }
    logging_middleware: LoggingMiddleware = LoggingMiddleware(app)

    await logging_middleware(scope, receive_mock, send_mock)

    assert len(caplog.messages) == 1


@pytest.mark.asyncio
async def test_submits_search_term_when_enabled(
    mocker: MockerFixture,
    receive_mock: Receive,
    send_mock: Send,
) -> None:
    """Test that a qualifying suggest request is enqueued for submission when enabled.

    Submission is decoupled from suggest-request logging: it happens even when
    LOG_SUGGEST_REQUEST is off.
    """
    log_data = mocker.MagicMock()
    mocker.patch("merino.middleware.logging.create_suggest_log_data", return_value=log_data)
    mocker.patch("merino.middleware.logging.SUBMIT_SEARCH_TERMS", True)
    mocker.patch.object(FeatureFlags, "is_enabled", return_value=True)
    mocker.patch("merino.middleware.logging.LOG_SUGGEST_REQUEST", False)
    handler = mocker.MagicMock()
    mocker.patch("merino.middleware.logging.get_message_handler", return_value=handler)

    logging_middleware: LoggingMiddleware = LoggingMiddleware(app)
    await logging_middleware(_suggest_scope(), receive_mock, send_mock)

    handler.put.assert_called_once_with(log_data.request_params)


@pytest.mark.asyncio
async def test_no_submission_when_disabled(
    mocker: MockerFixture,
    receive_mock: Receive,
    send_mock: Send,
) -> None:
    """Test that no search term is enqueued when submission is disabled."""
    mocker.patch("merino.middleware.logging.SUBMIT_SEARCH_TERMS", False)
    mocker.patch(
        "merino.middleware.logging.create_suggest_log_data",
        return_value=mocker.MagicMock(),
    )
    handler = mocker.MagicMock()
    mocker.patch("merino.middleware.logging.get_message_handler", return_value=handler)

    logging_middleware: LoggingMiddleware = LoggingMiddleware(app)
    await logging_middleware(_suggest_scope(), receive_mock, send_mock)

    handler.put.assert_not_called()


@pytest.mark.asyncio
async def test_no_submission_when_feature_flag_disabled(
    mocker: MockerFixture,
    receive_mock: Receive,
    send_mock: Send,
) -> None:
    """Test that no search term is enqueued when the feature flag buckets out the request."""
    mocker.patch("merino.middleware.logging.SUBMIT_SEARCH_TERMS", True)
    mocker.patch.object(FeatureFlags, "is_enabled", return_value=False)
    mocker.patch(
        "merino.middleware.logging.create_suggest_log_data",
        return_value=mocker.MagicMock(),
    )
    handler = mocker.MagicMock()
    mocker.patch("merino.middleware.logging.get_message_handler", return_value=handler)

    logging_middleware: LoggingMiddleware = LoggingMiddleware(app)
    await logging_middleware(_suggest_scope(), receive_mock, send_mock)

    handler.put.assert_not_called()


@pytest.mark.asyncio
async def test_submit_failure_does_not_break_request(
    mocker: MockerFixture,
    caplog: LogCaptureFixture,
    receive_mock: Receive,
    send_mock: Send,
) -> None:
    """Test that an enqueue failure is swallowed and does not fail the request."""
    mocker.patch(
        "merino.middleware.logging.create_suggest_log_data",
        return_value=mocker.MagicMock(),
    )
    mocker.patch("merino.middleware.logging.SUBMIT_SEARCH_TERMS", True)
    mocker.patch.object(FeatureFlags, "is_enabled", return_value=True)
    mocker.patch("merino.middleware.logging.LOG_SUGGEST_REQUEST", False)
    handler = mocker.MagicMock()
    handler.put.side_effect = QueueFullException("full")
    mocker.patch("merino.middleware.logging.get_message_handler", return_value=handler)

    caplog.set_level(logging.WARNING)
    logging_middleware: LoggingMiddleware = LoggingMiddleware(app)

    # Should not raise despite the queue being full.
    await logging_middleware(_suggest_scope(), receive_mock, send_mock)

    handler.put.assert_called_once()
    assert any("Failed to enqueue" in message for message in caplog.messages)


@pytest.mark.asyncio
async def test_submits_regardless_of_pii_flag(
    mocker: MockerFixture,
    caplog: LogCaptureFixture,
    receive_mock: Receive,
    send_mock: Send,
) -> None:
    """Test that a PII-flagged term is still submitted to fleece but not logged locally."""
    log_data = mocker.MagicMock()
    mocker.patch("merino.middleware.logging.create_suggest_log_data", return_value=log_data)
    mocker.patch("merino.middleware.logging.SUBMIT_SEARCH_TERMS", True)
    mocker.patch.object(FeatureFlags, "is_enabled", return_value=True)
    mocker.patch("merino.middleware.logging.LOG_SUGGEST_REQUEST", True)
    handler = mocker.MagicMock()
    mocker.patch("merino.middleware.logging.get_message_handler", return_value=handler)

    caplog.set_level(logging.INFO)
    scope = _suggest_scope()
    scope["merino_pii_detection"] = "email"
    logging_middleware: LoggingMiddleware = LoggingMiddleware(app)

    await logging_middleware(scope, receive_mock, send_mock)

    handler.put.assert_called_once_with(log_data.request_params)

    assert not any(record.name == "web.suggest.request" for record in caplog.records)


def _suggest_log_data() -> SuggestLogDataModel:
    """Return log data carrying real request params, so `submitted_at` is observable."""
    return SuggestLogDataModel(
        sensitive=True,
        mozlog=MozlogDataModel(
            errno=0,
            time=datetime(2022, 12, 18, tzinfo=UTC),
            path="/api/v1/suggest",
            method="GET",
        ),
        request_params=SuggestRequestParams(
            query="apple",
            code=200,
            rid="rid",
            client_variants="",
            requested_providers="wikipedia",
            browser="Firefox",
            os_family="macos",
            form_factor="desktop",
        ),
    )


@pytest.mark.asyncio
async def test_submitted_term_is_stamped_with_utc_timestamp(
    mocker: MockerFixture,
    receive_mock: Receive,
    send_mock: Send,
) -> None:
    """Test that an enqueued search term carries the UTC instant it was submitted."""
    log_data = _suggest_log_data()
    mocker.patch("merino.middleware.logging.create_suggest_log_data", return_value=log_data)
    mocker.patch("merino.middleware.logging.SUBMIT_SEARCH_TERMS", True)
    mocker.patch.object(FeatureFlags, "is_enabled", return_value=True)
    mocker.patch("merino.middleware.logging.LOG_SUGGEST_REQUEST", False)
    handler = mocker.MagicMock()
    mocker.patch("merino.middleware.logging.get_message_handler", return_value=handler)

    before = datetime.now(UTC)
    logging_middleware: LoggingMiddleware = LoggingMiddleware(app)
    await logging_middleware(_suggest_scope(), receive_mock, send_mock)

    submitted_at = handler.put.call_args.args[0].submitted_at
    assert submitted_at is not None
    assert submitted_at.tzinfo is not None
    assert submitted_at.utcoffset() == timedelta(0)
    assert before <= submitted_at <= datetime.now(UTC)


@pytest.mark.asyncio
async def test_no_timestamp_when_term_is_not_submitted(
    mocker: MockerFixture,
    caplog: LogCaptureFixture,
    receive_mock: Receive,
    send_mock: Send,
) -> None:
    """Test that the log-only path neither stamps nor logs a submission timestamp.

    The timestamp describes a submission to merino-fleece, so a request that is only
    logged has none, and the suggest request record never carries the field either way.
    """
    log_data = _suggest_log_data()
    mocker.patch("merino.middleware.logging.create_suggest_log_data", return_value=log_data)
    mocker.patch("merino.middleware.logging.SUBMIT_SEARCH_TERMS", False)
    mocker.patch("merino.middleware.logging.LOG_SUGGEST_REQUEST", True)

    caplog.set_level(logging.INFO)
    logging_middleware: LoggingMiddleware = LoggingMiddleware(app)
    await logging_middleware(_suggest_scope(), receive_mock, send_mock)

    assert log_data.request_params.submitted_at is None
    records = [record for record in caplog.records if record.name == "web.suggest.request"]
    assert len(records) == 1
    assert not hasattr(records[0], "submitted_at")
