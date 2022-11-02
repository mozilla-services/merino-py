# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import pytest
from starlette.testclient import TestClient

from merino.main import app


@pytest.fixture(name="client")
def fixture_test_client() -> TestClient:
    """Return a FastAPI TestClient instance for use in test methods"""
    return TestClient(app)
