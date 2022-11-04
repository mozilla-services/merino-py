# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import aiodogstatsd
import pytest
from fastapi.testclient import TestClient
from pytest_mock import MockerFixture

from tests.integration.api.v1.models import (
    CorruptProvider,
    NonsponsoredProvider,
    SponsoredProvider,
)


@pytest.mark.parametrize(
    "providers",
    [
        {
            "sponsored-provider": SponsoredProvider(enabled_by_default=True),
            "nonsponsored-provider": NonsponsoredProvider(enabled_by_default=True),
        }
    ],
)
@pytest.mark.parametrize(
    ["url", "metric_keys"],
    [
        (
            "/api/v1/suggest?q=none",
            ["get.api.v1.suggest.timing", "get.api.v1.suggest.status_codes.200"],
        ),
        (
            "/api/v1/nonono",
            ["response.status_codes.404"],
        ),
        (
            "/api/v1/suggest",
            ["get.api.v1.suggest.timing", "get.api.v1.suggest.status_codes.400"],
        ),
        ("/__error__", ["get.__error__.timing", "get.__error__.status_codes.500"]),
    ],
)
def test_metrics(
    mocker: MockerFixture,
    client: TestClient,
    url: str,
    metric_keys: list[str],
) -> None:
    report = mocker.patch.object(aiodogstatsd.Client, "_report")

    client.get(url)
    for metric in metric_keys:
        report.assert_any_call(metric, mocker.ANY, mocker.ANY, mocker.ANY, mocker.ANY)


@pytest.mark.skip(reason="currently no feature flags in use")
@pytest.mark.parametrize(
    ["url", "metric_keys", "tags"],
    [
        (
            "/api/v1/suggest?q=none",
            [
                "get.api.v1.suggest.timing",
                "get.api.v1.suggest.status_codes.200",
                "providers.adm.query",
                "providers.wiki_fruit.query",
                "providers.top_picks.query",
                "response.status_codes.200",
            ],
            [
                "feature_flag.test-perc-enabled",
                "feature_flag.test-perc-enabled-session",
            ],
        ),
        ("/api/v1/nonono", ["response.status_codes.404"], []),
        (
            "/api/v1/suggest",
            [
                "get.api.v1.suggest.timing",
                "get.api.v1.suggest.status_codes.400",
                "response.status_codes.400",
            ],
            [],
        ),
        (
            "/__error__",
            [
                "get.__error__.timing",
                "get.__error__.status_codes.500",
                "response.status_codes.500",
            ],
            [],
        ),
    ],
    ids=["200_with_feature_flags_tags", "404_no_tags", "400_no_tags", "500_no_tags"],
)
def test_feature_flags(
    mocker: MockerFixture, client: TestClient, url: str, metric_keys: list, tags: list
):
    """Test that feature flags are added for successful requests."""
    report = mocker.patch.object(aiodogstatsd.Client, "_report")

    client.get(url)

    want = {metric_key: tags for metric_key in metric_keys}

    # TODO: This is not great. We're relying on internal details of aiodogstatsd
    # here Can we record calls to the metrics client instead?
    got = {call.args[0]: [*call.args[3].keys()] for call in report.call_args_list}

    assert got == want


@pytest.mark.parametrize("providers", [{"corrupt": CorruptProvider()}])
def test_metrics_500(mocker: MockerFixture, client: TestClient) -> None:
    """Test that 500 status codes are recorded as metrics."""
    error_msg = "test"
    metric_keys = [
        "get.api.v1.suggest.timing",
        "get.api.v1.suggest.status_codes.500",
    ]

    report = mocker.patch.object(aiodogstatsd.Client, "_report")

    with pytest.raises(RuntimeError) as excinfo:
        client.get(f"/api/v1/suggest?q={error_msg}")

    for metric in metric_keys:
        report.assert_any_call(metric, mocker.ANY, mocker.ANY, mocker.ANY, mocker.ANY)

    assert str(excinfo.value) == error_msg
