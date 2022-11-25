# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the middleware user_agent module."""

import pytest
from pytest_mock import MockerFixture
from starlette.types import ASGIApp, Receive, Scope, Send

from merino.middleware import ScopeKey
from merino.middleware.user_agent import UserAgent, UserAgentMiddleware


@pytest.fixture(name="user_agent_middleware")
def fixture_user_agent_middleware(mocker: MockerFixture) -> UserAgentMiddleware:
    """Create a UserAgentMiddleware object for test"""
    asgiapp_mock = mocker.AsyncMock(spec=ASGIApp)
    return UserAgentMiddleware(asgiapp_mock)


@pytest.mark.asyncio
async def test_user_agent_parsing(
    user_agent_middleware: UserAgentMiddleware,
    scope: Scope,
    receive_mock: Receive,
    send_mock: Send,
):
    """Test the proper assignment of UserAgent properties given a request IP address."""
    expected_user_agent = UserAgent(
        browser="Firefox(103.0)", os_family="macos", form_factor="desktop"
    )

    scope["headers"] = [
        (
            b"user-agent",
            (
                b"Mozilla/5.0 (Macintosh; Intel Mac OS X 11.2; rv:85.0) Gecko/20100101"
                b" Firefox/103.0"
            ),
        )
    ]

    await user_agent_middleware(scope, receive_mock, send_mock)

    assert scope[ScopeKey.USER_AGENT] == expected_user_agent


@pytest.mark.asyncio
async def test_user_agent_invalid_scope_type(
    user_agent_middleware: UserAgentMiddleware,
    receive_mock: Receive,
    send_mock: Send,
) -> None:
    """Test that no user agent assignment takes place for an unexpected Scope type."""
    scope: Scope = {"type": "not-http"}

    await user_agent_middleware(scope, receive_mock, send_mock)

    assert ScopeKey.USER_AGENT not in scope
