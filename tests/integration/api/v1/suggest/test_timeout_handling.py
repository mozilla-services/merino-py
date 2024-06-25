# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Integration tests for the Merino v1 suggest API endpoint focusing on time out
behavior.
"""

from collections import namedtuple

import aiodogstatsd
import pytest
from fastapi.testclient import TestClient
from pytest import LogCaptureFixture
from pytest_mock import MockerFixture

from tests.integration.api.v1.fake_providers import FakeProviderFactory
from tests.types import FilterCaplogFixture

Scenario = namedtuple(
    "Scenario",
    [
        "providers",
        "expected_suggestion_count",
        "expected_logs_on_task_runner",
        "expected_metric_keys",
    ],
)

SCENARIOS: dict[str, Scenario] = {
    # Case I: Only one provider that will time out.
    #
    #   - Expects:
    #     - No suggestions
    #     - Timeout logs recorded in the task runner
    #     - Timeout metrics recorded in the task runner
    "Case-I: A-timed-out-provider": Scenario(
        providers={
            "timedout-sponsored": FakeProviderFactory.timeout_sponsored(enabled_by_default=True),
        },
        expected_suggestion_count=0,
        expected_logs_on_task_runner={
            "Timeout triggered in the task runner",
            "Cancelling the task: timedout-sponsored due to timeout",
        },
        expected_metric_keys={
            "providers.timedout-sponsored.query",
            "providers.timedout-sponsored.query.timeout",
            "suggestions-per.request",
            "suggestions-per.provider.timedout-sponsored",
            "get.api.v1.suggest.timing",
            "get.api.v1.suggest.status_codes.200",
            "response.status_codes.200",
        },
    ),
    # Case II: One provider that will time out and another one will not.
    #
    #   - Expects:
    #     - 1 suggestion returned from the non-timedout provider
    #     - Timeout logs recorded in the task runner
    #     - Timeout metrics recorded in the task runner
    "Case-II: A-non-timed-out-and-a-timed-out-providers": Scenario(
        providers={
            "sponsored": FakeProviderFactory.sponsored(enabled_by_default=True),
            "timedout-sponsored": FakeProviderFactory.timeout_sponsored(enabled_by_default=True),
        },
        expected_suggestion_count=1,
        expected_logs_on_task_runner={
            "Timeout triggered in the task runner",
            "Cancelling the task: timedout-sponsored due to timeout",
        },
        expected_metric_keys={
            "providers.sponsored.query",
            "providers.timedout-sponsored.query",
            "providers.timedout-sponsored.query.timeout",
            "suggestions-per.request",
            "suggestions-per.provider.sponsored",
            "suggestions-per.provider.timedout-sponsored",
            "get.api.v1.suggest.timing",
            "get.api.v1.suggest.status_codes.200",
            "response.status_codes.200",
        },
    ),
    # Case III: One provider that should not time out since it uses the custom timeout
    #           which is larger than its query duration.
    #
    #   - Expects:
    #     - 1 suggestion returned from this provider
    #     - Timeout logs should not be recorded in the task runner
    #     - Timeout metrics should not be recorded in the task runner
    "Case-III: A-timed-out-tolerant-provider": Scenario(
        providers={
            "timedout-tolerant-sponsored": FakeProviderFactory.timeout_tolerant_sponsored(
                enabled_by_default=True
            ),
        },
        expected_suggestion_count=1,
        expected_logs_on_task_runner=set(),
        expected_metric_keys={
            "providers.timedout-tolerant-sponsored.query",
            "suggestions-per.request",
            "suggestions-per.provider.timedout-tolerant-sponsored",
            "get.api.v1.suggest.timing",
            "get.api.v1.suggest.status_codes.200",
            "response.status_codes.200",
        },
    ),
    # Case IV: A regular non-timedout provider, a timed-out-tolerant provider, and a timed-out
    #          provider.
    #
    #   - Expects:
    #     - 3 suggestions returned from all three providers since the max timeout is overridden
    #       by the timed-out-tolerant provider
    #     - Timeout logs should not be recorded in the task runner
    #     - Timeout metrics should not be recorded in the task runner
    "Case-IV: A-non-timed-out-and-a-timed-out-tolerant-and-a-timed-out-providers": Scenario(
        providers={
            "sponsored": FakeProviderFactory.sponsored(enabled_by_default=True),
            "timedout-sponsored": FakeProviderFactory.timeout_sponsored(enabled_by_default=True),
            "timedout-tolerant-sponsored": FakeProviderFactory.timeout_tolerant_sponsored(
                enabled_by_default=True
            ),
        },
        expected_suggestion_count=3,
        expected_logs_on_task_runner=set(),
        expected_metric_keys={
            "providers.sponsored.query",
            "providers.timedout-sponsored.query",
            "providers.timedout-tolerant-sponsored.query",
            "suggestions-per.request",
            "suggestions-per.provider.timedout-tolerant-sponsored",
            "suggestions-per.provider.timedout-sponsored",
            "suggestions-per.provider.sponsored",
            "get.api.v1.suggest.timing",
            "get.api.v1.suggest.status_codes.200",
            "response.status_codes.200",
        },
    ),
}


@pytest.mark.parametrize(
    argnames=[
        "providers",
        "expected_suggestion_count",
        "expected_logs_on_task_runner",
        "expected_metric_keys",
    ],
    argvalues=SCENARIOS.values(),
    ids=SCENARIOS.keys(),
)
def test_timedout_providers(
    mocker: MockerFixture,
    client: TestClient,
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
    expected_suggestion_count: int,
    expected_logs_on_task_runner: set[str],
    expected_metric_keys: set[str],
) -> None:
    """Test that the suggest endpoint response is as expected for providers with
    different timeout settings.
    """
    report = mocker.patch.object(aiodogstatsd.Client, "_report")

    response = client.get("/api/v1/suggest?q=sponsored")
    assert response.status_code == 200

    # Check the completed query(-ies) should be returned
    result = response.json()
    assert len(result["suggestions"]) == expected_suggestion_count

    # Check logs for the timed out query(-ies)
    records = filter_caplog(caplog.records, "merino.utils.task_runner")

    assert {record.__dict__["msg"] for record in records} == expected_logs_on_task_runner

    # Check metrics for the timed out query(-ies)
    assert {call.args[0] for call in report.call_args_list} == expected_metric_keys
