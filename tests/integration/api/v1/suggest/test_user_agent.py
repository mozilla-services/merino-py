# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import logging

import pytest
from fastapi.testclient import TestClient
from pytest import LogCaptureFixture
from pytest_mock import MockerFixture

from tests.integration.api.v1.models import NonsponsoredProvider, SponsoredProvider
from tests.integration.api.v1.types import Providers
from tests.types import FilterCaplogFixture


@pytest.fixture(name="providers")
def fixture_providers() -> Providers:
    """Define providers for this module which are injected automatically."""
    return {
        "sponsored-provider": SponsoredProvider(enabled_by_default=True),
        "nonsponsored-provider": NonsponsoredProvider(enabled_by_default=True),
    }


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
    assert record.__dict__["browser"] == "Firefox(103.0)"
    assert record.__dict__["os_family"] == "macos"
    assert record.__dict__["form_factor"] == "desktop"


def test_user_agent_middleware_with_missing_ua_str(
    mocker: MockerFixture,
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
    client: TestClient,
) -> None:
    caplog.set_level(logging.INFO)

    mock_client = mocker.patch("fastapi.Request.client")
    mock_client.host = "127.0.0.1"

    client.get("/api/v1/suggest?q=nope", headers={})

    records = filter_caplog(caplog.records, "web.suggest.request")

    assert len(records) == 1

    record = records[0]
    assert record.__dict__["browser"] == "Other"
    assert record.__dict__["os_family"] == "other"
    assert record.__dict__["form_factor"] == "other"
