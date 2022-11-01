# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import logging

from fastapi.testclient import TestClient
from pytest import LogCaptureFixture

from tests.conftest import FilterCaplogFixture


def test_error(
    client: TestClient, caplog: LogCaptureFixture, filter_caplog: FilterCaplogFixture
) -> None:
    """
    Test that the error endpoint is supported to conform to dockerflow
    """
    caplog.set_level(logging.ERROR)

    response = client.get("/__error__")

    assert response.status_code == 500
    records = filter_caplog(caplog.records, "merino.web.dockerflow")
    assert len(records) == 1
    assert records[0].message == "The __error__ endpoint was called"
