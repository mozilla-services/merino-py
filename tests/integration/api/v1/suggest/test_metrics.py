# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import unittest.mock as mock

import aiodogstatsd
import pytest
from fastapi.testclient import TestClient
from pytest_mock import MockerFixture

from merino.providers import BaseProvider
from tests.integration.api.v1.conftest import (
    CorruptProvider,
    NonsponsoredProvider,
    SetupProvidersFixture,
    SponsoredProvider,
    TeardownProvidersFixture,
)


@pytest.fixture(autouse=True)
def inject_providers(teardown_providers: TeardownProvidersFixture):
    yield
    teardown_providers()


@pytest.mark.parametrize(
    "url,metric_keys",
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
        (
            "/__error__",
            ["get.__error__.timing", "get.__error__.status_codes.500"],
        ),
    ],
)
def test_metrics(
    client: TestClient,
    setup_providers: SetupProvidersFixture,
    url: str,
    metric_keys: [str],
) -> None:
    providers: dict[str, BaseProvider] = {
        "sponsored-provider": SponsoredProvider(enabled_by_default=True),
        "nonsponsored-provider": NonsponsoredProvider(enabled_by_default=True),
    }
    setup_providers(providers)

    with mock.patch.object(aiodogstatsd.Client, "_report") as reporter:
        client.get(url)
        for metric in metric_keys:
            reporter.assert_any_call(metric, mock.ANY, mock.ANY, mock.ANY, mock.ANY)


def test_metrics_500(
    mocker: MockerFixture, client: TestClient, setup_providers: SetupProvidersFixture
) -> None:
    providers: dict[str, BaseProvider] = {"corrupt": CorruptProvider()}
    setup_providers(providers)

    error_msg = "test"
    metric_keys = [
        "get.api.v1.suggest.timing",
        "get.api.v1.suggest.status_codes.500",
    ]

    reporter = mocker.patch.object(aiodogstatsd.Client, "_report")

    with pytest.raises(RuntimeError) as excinfo:
        client.get(f"/api/v1/suggest?q={error_msg}")

    for metric in metric_keys:
        reporter.assert_any_call(metric, mock.ANY, mock.ANY, mock.ANY, mock.ANY)

    assert str(excinfo.value) == error_msg
