# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from typing import Iterator

import pytest
from starlette.testclient import TestClient

from merino.main import app


@pytest.fixture(name="client")
def fixture_test_client() -> TestClient:
    """Return a FastAPI TestClient instance.

    Note that this will NOT trigger event handlers (i.e. `startup` and `shutdown`) for
    the app, see: https://fastapi.tiangolo.com/advanced/testing-events/
    """
    return TestClient(app)


@pytest.fixture(name="client_with_events")
def fixture_test_client_with_events() -> Iterator[TestClient]:
    """Return a FastAPI TestClient instance.

    This test client will trigger event handlers for the app, see:
    https://fastapi.tiangolo.com/advanced/testing-events/
    """
    with TestClient(app) as client:
        yield client
