# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Integration tests for the Merino __version__ API endpoint."""

import logging
import pathlib
from logging import LogRecord

from fastapi.testclient import TestClient
from freezegun import freeze_time
from pytest import LogCaptureFixture
from pytest_mock import MockerFixture

from merino.utils.log_data_creators import RequestSummaryLogDataModel
from tests.integration.api.types import RequestSummaryLogDataFixture
from tests.types import FilterCaplogFixture


def test_version(client: TestClient) -> None:
    """Test that the version endpoint conforms to dockerflow specifications."""
    response = client.get("/__version__")

    assert response.status_code == 200
    result = response.json()
    assert "source" in result
    assert "version" in result
    assert "commit" in result
    assert "build" in result


def test_version_error(mocker: MockerFixture, client: TestClient) -> None:
    """Test that the version endpoint returns a 500 status if an error occurs while
    evaluating the response.
    """
    mocker.patch.object(pathlib.Path, "read_text", side_effect=FileNotFoundError)

    response = client.get("/__version__")

    assert response.status_code == 500
    assert response.json() == {"detail": "Version file does not exist"}


@freeze_time("1998-03-31")
def test_version_request_log_data(
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
    extract_request_summary_log_data: RequestSummaryLogDataFixture,
    client: TestClient,
) -> None:
    """Test that the request log for the '__version__' endpoint contains the required
    extra data.
    """
    caplog.set_level(logging.INFO)

    expected_log_data: RequestSummaryLogDataModel = RequestSummaryLogDataModel(
        agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 11.2; rv:85.0)"
            " Gecko/20100101 Firefox/103.0"
        ),
        path="/__version__",
        method="GET",
        lang="en-US",
        querystring={},
        errno=0,
        code=200,
        time="1998-03-31T00:00:00",
    )

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
    log_data: RequestSummaryLogDataModel = extract_request_summary_log_data(record)
    assert log_data == expected_log_data
