# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import logging

import pytest
from fastapi.testclient import TestClient
from pytest import LogCaptureFixture
from pytest_mock import MockerFixture

from tests.types import FilterCaplogFixture


@pytest.mark.parametrize("endpoint", ["__heartbeat__", "__lbheartbeat__"])
def test_heartbeats(client: TestClient, endpoint: str) -> None:
    """Test that the heartbeat endpoint is supported to conform to dockerflow"""
    response = client.get(f"/{endpoint}")

    assert response.status_code == 200


def test_non_suggest_request_logs_contain_required_info(
    mocker: MockerFixture,
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
    client: TestClient,
) -> None:
    caplog.set_level(logging.INFO)

    # Use a valid IP to avoid the geolocation errors/logs
    mock_client = mocker.patch("fastapi.Request.client")
    mock_client.host = "127.0.0.1"

    client.get("/__heartbeat__")

    records = filter_caplog(caplog.records, "request.summary")
    assert len(records) == 1

    record = records[0]
    assert record.name == "request.summary"
    assert "country" not in record.__dict__["args"]
    assert "session_id" not in record.__dict__["args"]
    assert record.__dict__["path"] == "/__heartbeat__"
