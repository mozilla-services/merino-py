# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Integration tests for unsupported Merino v1 API endpoints."""

import logging
from logging import LogRecord
from typing import Any

import pytest
from fastapi.testclient import TestClient
from freezegun import freeze_time
from pytest import LogCaptureFixture

from tests.integration.api.types import LogDataFixture
from tests.types import FilterCaplogFixture


@freeze_time("1998-03-31")
@pytest.mark.parametrize("providers", [{}])
def test_unsupported_request_log_data(
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
    log_data: LogDataFixture,
    client: TestClient,
) -> None:
    """
    Tests that the request logs for to unsupported endpoints contain the required
    extra data
    """
    caplog.set_level(logging.INFO)

    expected_log_data: dict[str, Any] = {
        "name": "request.summary",
        "agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 11.2; rv:85.0)"
            " Gecko/20100101 Firefox/103.0"
        ),
        "path": "/api/v1/unknown",
        "method": "GET",
        "lang": "en-US",
        "querystring": {},
        "errno": 0,
        "code": 404,
        "time": "1998-03-31T00:00:00",
    }

    client.get(
        "/api/v1/unknown",
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
    assert log_data(record) == expected_log_data
