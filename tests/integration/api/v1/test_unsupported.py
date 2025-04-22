# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Integration tests for unsupported Merino v1 API endpoints."""

import aiodogstatsd
from fastapi.testclient import TestClient
from pytest_mock import MockerFixture


def test_unsupported_endpoint_metrics(mocker: MockerFixture, client: TestClient) -> None:
    """Test that metrics are recorded for unsupported endpoints (status code 404)."""
    expected_metric_keys: list[str] = ["response.status_codes.404"]

    report = mocker.patch.object(aiodogstatsd.Client, "_report")

    client.get("/api/v1/unsupported")

    # TODO: Remove reliance on internal details of aiodogstatsd
    metric_keys: list[str] = [call.args[0] for call in report.call_args_list]
    assert metric_keys == expected_metric_keys
