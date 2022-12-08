# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Integration tests for the Merino __heartbeat__ and __lbheartbeat__ API endpoints."""

import logging
from logging import LogRecord

import pytest
from _pytest.logging import LogCaptureFixture
from fastapi.testclient import TestClient
from freezegun import freeze_time

from merino.utils.log_data_creators import RequestSummaryLogDataModel
from tests.integration.api.types import RequestSummaryLogDataFixture
from tests.types import FilterCaplogFixture


@pytest.mark.parametrize("endpoint", ["__heartbeat__", "__lbheartbeat__"])
def test_heartbeats(client: TestClient, endpoint: str) -> None:
    """Test that the heartbeat endpoint is supported to conform to dockerflow"""
    response = client.get(f"/{endpoint}")

    assert response.status_code == 200


@freeze_time("1998-03-31")
@pytest.mark.parametrize("endpoint", ["__heartbeat__", "__lbheartbeat__"])
def test_heartbeat_request_log_data(
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
    extract_request_summary_log_data: RequestSummaryLogDataFixture,
    client: TestClient,
    endpoint: str,
) -> None:
    """Test that the request log for the '__heartbeat__' and '__lbheartbeat__'
    endpoints contain the required extra data
    """
    caplog.set_level(logging.INFO)

    expected_log_data: RequestSummaryLogDataModel = RequestSummaryLogDataModel(
        agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 11.2; rv:85.0)"
            " Gecko/20100101 Firefox/103.0"
        ),
        path=f"/{endpoint}",
        method="GET",
        lang="en-US",
        querystring={},
        errno=0,
        code=200,
        time="1998-03-31T00:00:00",
    )

    client.get(
        f"/{endpoint}",
        headers={
            "accept-language": "en-US",
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 11.2; rv:85.0) "
                "Gecko/20100101 Firefox/103.0"
            ),
        },
    )

    records: list[LogRecord] = filter_caplog(caplog.records, "request.summary")
    assert len(records) == 1

    record: LogRecord = records[0]
    log_data: RequestSummaryLogDataModel = extract_request_summary_log_data(record)
    assert log_data == expected_log_data
