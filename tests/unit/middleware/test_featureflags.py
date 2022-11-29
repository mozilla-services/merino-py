# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the middleware featureflags module."""

import pytest
from pytest_mock import MockerFixture
from starlette.types import ASGIApp, Receive, Scope, Send

from merino.featureflags import session_id_context
from merino.middleware.featureflags import FeatureFlagsMiddleware


@pytest.fixture(name="featureflags_middleware")
def fixture_featureflags_middleware(mocker: MockerFixture) -> FeatureFlagsMiddleware:
    """Create a FeatureFlagsMiddleware object for test."""
    asgiapp_mock = mocker.AsyncMock(spec=ASGIApp)
    return FeatureFlagsMiddleware(asgiapp_mock)


@pytest.mark.asyncio
async def test_featureflags_sid_found(
    featureflags_middleware: FeatureFlagsMiddleware,
    scope: Scope,
    receive_mock: Receive,
    send_mock: Send,
) -> None:
    """Test that SID is assigned given an `sid` query parameter."""
    expected_sid: str = "9aadf682-2f7a-4ad1-9976-dc30b60451d8"
    scope["query_string"] = f"q=nope&sid={expected_sid}"

    await featureflags_middleware(scope, receive_mock, send_mock)

    assert session_id_context.get() == expected_sid


@pytest.mark.asyncio
async def test_featureflags_sid_not_found(
    featureflags_middleware: FeatureFlagsMiddleware,
    scope: Scope,
    receive_mock: Receive,
    send_mock: Send,
) -> None:
    """Test that SID is assigned `None` if `sid` query parameter is not available."""
    scope["query_string"] = "q=nope"

    await featureflags_middleware(scope, receive_mock, send_mock)

    assert session_id_context.get() is None


@pytest.mark.asyncio
async def test_featureflags_invalid_scope_type(
    featureflags_middleware: FeatureFlagsMiddleware,
    receive_mock: Receive,
    send_mock: Send,
) -> None:
    """Test that no SID assignment takes place for an unexpected Scope type."""
    scope: Scope = {"type": "not-http"}

    await featureflags_middleware(scope, receive_mock, send_mock)

    assert session_id_context.get() == "fff"
