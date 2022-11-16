# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Module for test fixtures for the middleware unit test directory."""

from typing import Any

import pytest
from pytest_mock import MockerFixture
from starlette.types import Receive, Scope, Send


@pytest.fixture(name="scope")
def fixture_scope() -> Scope:
    """Create a Scope object for test"""
    scope: Scope = {"type": "http"}
    return scope


@pytest.fixture(name="receive_mock")
def fixture_receive_mock(mocker: MockerFixture) -> Any:
    """Create a Receive mock object for test"""
    return mocker.AsyncMock(spec=Receive)


@pytest.fixture(name="send_mock")
def fixture_send_mock(mocker: MockerFixture) -> Any:
    """Create a Send mock object for test"""
    return mocker.AsyncMock(spec=Send)
