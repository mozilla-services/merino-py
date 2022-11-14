# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Integration tests for the Merino __version__ API endpoint."""

import logging
from logging import LogRecord
from typing import Any

from fastapi.testclient import TestClient
from freezegun import freeze_time
from pytest import LogCaptureFixture
from pytest_mock import MockerFixture

from tests.integration.api.types import LogDataFixture
from tests.types import FilterCaplogFixture


def test_version(client: TestClient) -> None:
    """Test that the version endpoint is supported to conform to dockerflow"""
    response = client.get("/__version__")

    assert response.status_code == 200
    result = response.json()
    assert "source" in result
    assert "version" in result
    assert "commit" in result
    assert "build" in result


def test_version_error(mocker: MockerFixture, client: TestClient) -> None:
    mocker.patch("os.path.exists", return_value=False)

    response = client.get("/__version__")

    assert response.status_code == 500


@freeze_time("1998-03-31")
def test_version_request_log_data(
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
    log_data: LogDataFixture,
    client: TestClient,
) -> None:
    """
    Test that the request log for the '__version__' endpoint contains the required
    extra data
    """
    caplog.set_level(logging.INFO)

    expected_log_data: dict[str, Any] = {
        "name": "request.summary",
        "agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 11.2; rv:85.0)"
            " Gecko/20100101 Firefox/103.0"
        ),
        "path": "/__version__",
        "method": "GET",
        "lang": "en-US",
        "querystring": {},
        "errno": 0,
        "code": 200,
        "time": "1998-03-31T00:00:00",
    }

    client.get(
        "/__version__",
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
