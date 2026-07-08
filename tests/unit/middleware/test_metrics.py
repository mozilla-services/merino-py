# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the middleware metrics module."""

import logging
from unittest.mock import MagicMock

import pytest
from pytest import LogCaptureFixture
from pytest_mock import MockerFixture
from starlette.types import ASGIApp, Receive, Scope, Send

from merino.middleware import ScopeKey
from merino.middleware.metrics import MetricsMiddleware
from merino.middleware.user_agent import UserAgent


@pytest.mark.asyncio
async def test_metrics_invalid_scope_type(
    mocker: MockerFixture,
    caplog: LogCaptureFixture,
    receive_mock: Receive,
    send_mock: Send,
) -> None:
    """Test that no logging action takes place for an unexpected Scope type."""
    caplog.set_level(logging.INFO)
    scope: Scope = {"type": "not-http"}
    metrics_middleware: MetricsMiddleware = MetricsMiddleware(mocker.AsyncMock(spec=ASGIApp))

    await metrics_middleware(scope, receive_mock, send_mock)

    assert len(caplog.messages) == 0


def _http_scope(path: str = "/api/v1/suggest") -> Scope:
    """Build a minimal HTTP scope carrying a parsed user agent with a versioned browser."""
    return {
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": [],
        "query_string": b"",
        ScopeKey.USER_AGENT: UserAgent(
            browser="Firefox(104.0.1)", os_family="macos", form_factor="desktop"
        ),
    }


def _responding_app(status_code: int) -> ASGIApp:
    """Return an ASGI app that emits a single response.start with the given status."""

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": status_code, "headers": []})

    return app


def _raising_app(exc: Exception) -> ASGIApp:
    """Return an ASGI app that raises the given exception without sending a response."""

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        raise exc

    return app


def _build_middleware(
    mocker: MockerFixture, app: ASGIApp
) -> tuple[MetricsMiddleware, MagicMock, MagicMock]:
    """Build a MetricsMiddleware with mocked otel instruments.

    Returns the middleware along with the mocked (counter, histogram), so tests can assert
    on the exact attributes our code passes to them.
    """
    counter = mocker.MagicMock(name="counter")
    histogram = mocker.MagicMock(name="histogram")
    meter = mocker.MagicMock()
    meter.create_counter.return_value = counter
    meter.create_histogram.return_value = histogram
    mocker.patch("merino.middleware.metrics.metrics.get_meter", return_value=meter)
    # The middleware still stores a metrics client in the request scope for downstream use;
    # stub it out to avoid touching the real (memoized) StatsD client / network.
    mocker.patch("merino.middleware.metrics.get_metrics_client", return_value=mocker.MagicMock())

    return MetricsMiddleware(app), counter, histogram


@pytest.mark.asyncio
async def test_metrics_otel_attributes(
    mocker: MockerFixture,
    receive_mock: Receive,
    send_mock: Send,
) -> None:
    """Test the otel attributes our code emits: bounded tags only, no browser version."""
    middleware, counter, histogram = _build_middleware(mocker, _responding_app(200))

    await middleware(_http_scope(), receive_mock, send_mock)

    # The attribute dict is the second positional arg to record()/add().
    _, duration_attrs = histogram.record.call_args.args
    _, status_attrs = counter.add.call_args.args

    assert duration_attrs == {
        "method": "GET",
        "path": "/api/v1/suggest",
        "form_factor": "desktop",
        **MetricsMiddleware.constant_tags,
    }
    assert status_attrs == {
        "method": "GET",
        "path": "/api/v1/suggest",
        "status_code": 200,
        "form_factor": "desktop",
        **MetricsMiddleware.constant_tags,
    }
    # The high-cardinality browser version must not leak into otel tags.
    assert "browser" not in status_attrs


@pytest.mark.asyncio
async def test_metrics_otel_404_counter_omits_path(
    mocker: MockerFixture,
    receive_mock: Receive,
    send_mock: Send,
) -> None:
    """Test that 404 responses emit the status counter without the unbounded path tag.

    The duration histogram is not recorded for 404s at all.
    """
    middleware, counter, histogram = _build_middleware(mocker, _responding_app(404))

    await middleware(_http_scope("/api/v1/unsupported"), receive_mock, send_mock)

    # No duration histogram for 404s.
    histogram.record.assert_not_called()

    # The counter is emitted, but without `path` (404 paths are unbounded).
    _, status_attrs = counter.add.call_args.args
    assert status_attrs == {
        "method": "GET",
        "status_code": 404,
        "form_factor": "desktop",
        **MetricsMiddleware.constant_tags,
    }
    assert "path" not in status_attrs


@pytest.mark.asyncio
async def test_metrics_records_500_on_unhandled_exception(
    mocker: MockerFixture,
    receive_mock: Receive,
    send_mock: Send,
) -> None:
    """Test that an unhandled exception records 500 otel metrics and re-raises."""
    error = RuntimeError("boom")
    middleware, counter, histogram = _build_middleware(mocker, _raising_app(error))

    with pytest.raises(RuntimeError, match="boom"):
        await middleware(_http_scope(), receive_mock, send_mock)

    # The otel instruments are emitted with the 500 status and the same bounded tags.
    _, status_attrs = counter.add.call_args.args
    _, duration_attrs = histogram.record.call_args.args
    assert status_attrs == {
        "method": "GET",
        "path": "/api/v1/suggest",
        "status_code": 500,
        "form_factor": "desktop",
        **MetricsMiddleware.constant_tags,
    }
    assert duration_attrs == {
        "method": "GET",
        "path": "/api/v1/suggest",
        "form_factor": "desktop",
        **MetricsMiddleware.constant_tags,
    }
    assert "browser" not in status_attrs
