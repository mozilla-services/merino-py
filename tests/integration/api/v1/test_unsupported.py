# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Integration tests for unsupported Merino v1 API endpoints."""

import logging
from logging import LogRecord
from typing import Any

import aiodogstatsd
import pytest
from fastapi.testclient import TestClient
from freezegun import freeze_time
from pytest import LogCaptureFixture
from pytest_mock import MockerFixture

from tests.integration.api.types import RequestSummaryLogDataFixture
from tests.types import FilterCaplogFixture


@freeze_time("1998-03-31")
@pytest.mark.parametrize("providers", [{}])
def test_unsupported_endpoint_request_log_data(
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
    extract_request_summary_log_data: RequestSummaryLogDataFixture,
    client: TestClient,
) -> None:
    """
    Test that the request log for unsupported endpoints contains the required extra data
    """
    caplog.set_level(logging.INFO)

    expected_log_data: dict[str, Any] = {
        "name": "request.summary",
        "agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 11.2; rv:85.0)"
            " Gecko/20100101 Firefox/103.0"
        ),
        "path": "/api/v1/unsupported",
        "method": "GET",
        "lang": "en-US",
        "querystring": {},
        "errno": 0,
        "code": 404,
        "time": "1998-03-31T00:00:00",
    }

    client.get(
        "/api/v1/unsupported",
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
    log_data: dict[str, Any] = extract_request_summary_log_data(record)
    assert log_data == expected_log_data


@pytest.mark.parametrize("providers", [{}])
def test_unsupported_endpoint_metrics(
    mocker: MockerFixture, client: TestClient
) -> None:
    """Test that metrics are recorded for unsupported endpoints (status code 404)"""
    expected_metric_keys: list[str] = ["response.status_codes.404"]

    report = mocker.patch.object(aiodogstatsd.Client, "_report")

    client.get("/api/v1/unsupported")

    # TODO: Remove reliance on internal details of aiodogstatsd
    metric_keys: list[str] = [call.args[0] for call in report.call_args_list]
    assert metric_keys == expected_metric_keys


@pytest.mark.parametrize("providers", [{}])
def test_unsupported_endpoint_flags(mocker: MockerFixture, client: TestClient) -> None:
    """
    Test that feature flags are not added for unsupported endpoints (status code 404)
    """
    expected_tags_per_metric: dict[str, list[str]] = {"response.status_codes.404": []}

    report = mocker.patch.object(aiodogstatsd.Client, "_report")

    client.get("/api/v1/unsupported")

    # TODO: Remove reliance on internal details of aiodogstatsd
    tags_per_metric: dict[str, list[str]] = {
        call.args[0]: [*call.args[3].keys()] for call in report.call_args_list
    }
    assert tags_per_metric == expected_tags_per_metric
