# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the middleware metrics module."""

import logging

import pytest
from pytest import LogCaptureFixture
from pytest_mock import MockerFixture
from starlette.types import ASGIApp, Receive, Scope, Send

from merino.middleware.metrics import MetricsMiddleware


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
