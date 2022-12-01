# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Integration tests for the Merino v1 suggest API endpoint focusing on time out
behavior.
"""

import aiodogstatsd
import pytest
from fastapi.testclient import TestClient
from pytest import LogCaptureFixture
from pytest_mock import MockerFixture

from tests.integration.api.v1.fake_providers import (
    SponsoredProvider,
    TimeoutSponsoredProvider,
)
from tests.integration.api.v1.types import Providers
from tests.types import FilterCaplogFixture


@pytest.fixture(name="providers")
def fixture_providers() -> Providers:
    """Define providers for this module which are injected automatically."""
    return {
        "sponsored": SponsoredProvider(enabled_by_default=True),
        "timedout-sponsored": TimeoutSponsoredProvider(enabled_by_default=True),
    }


def test_with_timedout_provider(
    mocker: MockerFixture,
    client: TestClient,
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
) -> None:
    """Test that the suggest endpoint response is as expected when providers don't
    supply suggestions within a configured time limit.
    """
    report = mocker.patch.object(aiodogstatsd.Client, "_report")

    response = client.get("/api/v1/suggest?q=sponsored")
    assert response.status_code == 200

    # Check the completed query should be returned
    result = response.json()
    assert len(result["suggestions"]) == 1
    assert result["suggestions"][0]["full_keyword"] == "sponsored"
    assert result["request_id"] is not None

    # Check logs for the timed out query
    records = filter_caplog(caplog.records, "merino.utils.task_runner")

    assert len(records) == 2
    assert records[0].__dict__["msg"] == "Timeout triggered in the task runner"
    assert (
        records[1].__dict__["msg"]
        == "Cancelling the task: timedout-sponsored due to timeout"
    )

    # Check metrics for the timed out query
    expected_metric_keys = [
        "providers.sponsored.query",
        "providers.timedout-sponsored.query.timeout",
        "suggestions-per.request",
        # suggestions-per.provider gets called twice
        # because there are 2 providers specified in
        # injected into this test by fixture_providers
        "suggestions-per.provider",
        "suggestions-per.provider",
        "get.api.v1.suggest.timing",
        "get.api.v1.suggest.status_codes.200",
        "response.status_codes.200",
        "providers.timedout-sponsored.query",
    ]
    metric_keys: list[str] = [call.args[0] for call in report.call_args_list]
    assert metric_keys == expected_metric_keys
