# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Module for test configurations for the integration test directory."""

from logging import LogRecord
from typing import Any, Iterator

import pytest
from starlette.testclient import TestClient

from merino.main import app
from tests.integration.api.types import RequestSummaryLogDataFixture


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

    This test client will trigger event handlers (i.e. `startup` and `shutdown`) for
    the app, see: https://fastapi.tiangolo.com/advanced/testing-events/
    """
    with TestClient(app) as client:
        yield client


@pytest.fixture(name="extract_request_summary_log_data")
def fixture_extract_request_summary_log_data() -> RequestSummaryLogDataFixture:
    """
    Return a function that will extract the extra log data from a captured
    "request.summary" log record
    """

    def extract_request_summary_log_data(record: LogRecord) -> dict[str, Any]:
        return {
            "name": record.name,
            "errno": record.__dict__["errno"],
            "time": record.__dict__["time"],
            "agent": record.__dict__["agent"],
            "path": record.__dict__["path"],
            "method": record.__dict__["method"],
            "lang": record.__dict__["lang"],
            "querystring": record.__dict__["querystring"],
            "code": record.__dict__["code"],
        }

    return extract_request_summary_log_data
