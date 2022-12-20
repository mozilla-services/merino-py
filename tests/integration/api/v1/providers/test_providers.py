# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Integration tests for the Merino v1 providers API endpoint."""

import logging
from logging import LogRecord

import pytest
from fastapi.testclient import TestClient
from freezegun import freeze_time
from pytest import LogCaptureFixture

from merino.providers import BaseProvider
from merino.utils.log_data_creators import RequestSummaryLogDataModel
from tests.integration.api.types import RequestSummaryLogDataFixture
from tests.integration.api.v1.fake_providers import ProviderFactory
from tests.types import FilterCaplogFixture


@pytest.mark.parametrize(
    ["expected_response", "providers"],
    [
        ([], {}),
        (
            [
                {"id": "sponsored", "availability": "enabled_by_default"},
            ],
            {
                "sponsored": ProviderFactory.sponsored(enabled_by_default=True),
            },
        ),
        (
            [
                {"id": "sponsored", "availability": "disabled_by_default"},
            ],
            {
                "sponsored": ProviderFactory.sponsored(enabled_by_default=False),
            },
        ),
        (
            [
                {"id": "hidden-provider", "availability": "hidden"},
            ],
            {
                "hidden-provider": ProviderFactory.hidden(enabled_by_default=True),
            },
        ),
        (
            [
                {"id": "sponsored", "availability": "enabled_by_default"},
                {"id": "nonsponsored", "availability": "disabled_by_default"},
                {"id": "hidden-provider", "availability": "hidden"},
            ],
            {
                "sponsored": ProviderFactory.sponsored(enabled_by_default=True),
                "nonsponsored": ProviderFactory.nonsponsored(enabled_by_default=False),
                "hidden-provider": ProviderFactory.hidden(enabled_by_default=True),
            },
        ),
    ],
    ids=[
        "no-providers",
        "one-provider-enabled_by_default",
        "one-provider-disabled_by_default",
        "one-provider-hidden",
        "three-providers-all-availabilities",
    ],
)
def test_providers(
    client: TestClient,
    expected_response: list[dict[str, str]],
    providers: dict[str, BaseProvider],
) -> None:
    """Test that the response to the 'providers' endpoint is as expected when 0-to-many
    providers are registered with different availabilities
    """
    response = client.get("/api/v1/providers")

    assert response.status_code == 200
    assert response.json() == expected_response


@freeze_time("1998-03-31")
@pytest.mark.parametrize("providers", [{}])
def test_providers_request_log_data(
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
    extract_request_summary_log_data: RequestSummaryLogDataFixture,
    client: TestClient,
) -> None:
    """Test that the request log for the 'providers' endpoint contains the required
    extra data
    """
    caplog.set_level(logging.INFO)

    expected_log_data: RequestSummaryLogDataModel = RequestSummaryLogDataModel(
        agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 11.2; rv:85.0)"
            " Gecko/20100101 Firefox/103.0"
        ),
        path="/api/v1/providers",
        method="GET",
        lang="en-US",
        querystring={},
        errno=0,
        code=200,
        time="1998-03-31T00:00:00",
    )

    client.get(
        "/api/v1/providers",
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
