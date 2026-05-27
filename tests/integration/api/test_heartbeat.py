# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Integration tests for the Merino __heartbeat__ and __lbheartbeat__ API endpoints."""

import pytest
from fastapi.testclient import TestClient


@pytest.mark.parametrize("endpoint", ["__heartbeat__", "__lbheartbeat__"])
def test_heartbeats(client: TestClient, endpoint: str) -> None:
    """Test that the heartbeat endpoint is supported to conform to dockerflow"""
    response = client.get(f"/{endpoint}")

    assert response.status_code == 200
