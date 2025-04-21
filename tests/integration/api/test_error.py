# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Integration tests for the Merino __error__ API endpoint."""

import logging

import aiodogstatsd
from fastapi.testclient import TestClient
from pytest import LogCaptureFixture
from pytest_mock import MockerFixture

from tests.types import FilterCaplogFixture


def test_error(
    client: TestClient, caplog: LogCaptureFixture, filter_caplog: FilterCaplogFixture
) -> None:
    """Test that the error endpoint conforms to dockerflow specifications."""
    caplog.set_level(logging.ERROR)

    response = client.get("/__error__")

    assert response.status_code == 500
    records = filter_caplog(caplog.records, "merino.web.dockerflow")
    assert len(records) == 1
    assert records[0].message == "The __error__ endpoint was called"


def test_error_metrics(mocker: MockerFixture, client: TestClient) -> None:
    """Test that metrics are recorded for the '__error__' endpoint (status code 500)."""
    expected_metric_keys: list[str] = [
        "get.__error__.timing",
        "get.__error__.status_codes.500",
        "response.status_codes.500",
    ]

    report = mocker.patch.object(aiodogstatsd.Client, "_report")

    client.get("/__error__")

    # TODO: Remove reliance on internal details of aiodogstatsd
    metric_keys: list[str] = [call.args[0] for call in report.call_args_list]
    assert metric_keys == expected_metric_keys
