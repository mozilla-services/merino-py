# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import logging

import pytest
from fastapi.testclient import TestClient
from pytest import LogCaptureFixture
from pytest_mock import MockerFixture

from merino.providers import BaseProvider
from tests.conftest import FilterCaplogFixture
from tests.integration.api.v1.conftest import (
    NonsponsoredProvider,
    SetupProvidersFixture,
    SponsoredProvider,
    TeardownProvidersFixture,
)


@pytest.fixture(autouse=True)
def inject_providers(
    setup_providers: SetupProvidersFixture, teardown_providers: TeardownProvidersFixture
):
    providers: dict[str, BaseProvider] = {
        "sponsored-provider": SponsoredProvider(enabled_by_default=True),
        "nonsponsored-provider": NonsponsoredProvider(enabled_by_default=True),
    }
    setup_providers(providers)
    yield
    teardown_providers()


def test_user_agent_middleware(
    mocker: MockerFixture,
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
    client: TestClient,
) -> None:
    caplog.set_level(logging.INFO)

    mock_client = mocker.patch("fastapi.Request.client")
    mock_client.host = "127.0.0.1"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 11.2;"
            " rv:85.0) Gecko/20100101 Firefox/103.0"
        )
    }
    client.get("/api/v1/suggest?q=nope", headers=headers)

    records = filter_caplog(caplog.records, "web.suggest.request")

    assert len(records) == 1

    record = records[0]
    assert record.browser == "Firefox(103.0)"
    assert record.os_family == "macos"
    assert record.form_factor == "desktop"


def test_user_agent_middleware_with_missing_ua_str(
    mocker: MockerFixture,
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
    client: TestClient,
) -> None:
    caplog.set_level(logging.INFO)

    mock_client = mocker.patch("fastapi.Request.client")
    mock_client.host = "127.0.0.1"

    headers = {}
    client.get("/api/v1/suggest?q=nope", headers=headers)

    records = filter_caplog(caplog.records, "web.suggest.request")

    assert len(records) == 1

    record = records[0]
    assert record.browser == "Other"
    assert record.os_family == "other"
    assert record.form_factor == "other"
