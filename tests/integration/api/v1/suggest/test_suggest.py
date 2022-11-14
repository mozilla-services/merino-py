# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Integration tests for the Merino v1 suggest API endpoint."""

import logging
from typing import Any

import pytest
from fastapi.testclient import TestClient
from freezegun import freeze_time
from pytest import LogCaptureFixture
from pytest_mock import MockerFixture

from tests.integration.api.v1.fake_providers import (
    NonsponsoredProvider,
    SponsoredProvider,
)
from tests.integration.api.v1.types import Providers
from tests.types import FilterCaplogFixture


@pytest.fixture(name="providers")
def fixture_providers() -> Providers:
    """Define providers for this module which are injected automatically."""
    return {
        "sponsored-provider": SponsoredProvider(enabled_by_default=True),
        "nonsponsored-provider": NonsponsoredProvider(enabled_by_default=True),
    }


def test_suggest_sponsored(client: TestClient) -> None:
    response = client.get("/api/v1/suggest?q=sponsored")
    assert response.status_code == 200

    result = response.json()
    assert len(result["suggestions"]) == 1
    assert result["suggestions"][0]["full_keyword"] == "sponsored"
    assert result["request_id"] is not None


def test_suggest_nonsponsored(client: TestClient) -> None:
    response = client.get("/api/v1/suggest?q=nonsponsored")

    assert response.status_code == 200

    result = response.json()
    assert len(result["suggestions"]) == 1
    assert result["suggestions"][0]["full_keyword"] == "nonsponsored"
    assert result["request_id"] is not None


def test_no_suggestion(client: TestClient) -> None:
    response = client.get("/api/v1/suggest?q=nope")
    assert response.status_code == 200
    assert len(response.json()["suggestions"]) == 0


@pytest.mark.parametrize("query", ["sponsored", "nonsponsored"])
def test_suggest_from_missing_providers(client: TestClient, query: str) -> None:
    """
    Despite the keyword being available for other providers, it should not return any
    suggestions if the requested provider does not exist.
    """
    response = client.get(f"/api/v1/suggest?q={query}&providers=nonexist")
    assert response.status_code == 200
    assert len(response.json()["suggestions"]) == 0


def test_no_query_string(client: TestClient) -> None:
    response = client.get("/api/v1/suggest")
    assert response.status_code == 400


def test_client_variants(client: TestClient) -> None:
    response = client.get("/api/v1/suggest?q=sponsored&client_variants=foo,bar")
    assert response.status_code == 200

    result = response.json()
    assert len(result["suggestions"]) == 1
    assert result["client_variants"] == ["foo", "bar"]


@freeze_time("1998-03-31")
def test_suggest_request_log_data(
    mocker: MockerFixture,
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
    client: TestClient,
) -> None:
    """
    Tests that the request logs for the 'suggest' endpoint contain the required
    extra data
    """
    caplog.set_level(logging.INFO)

    # The IP address is taken from `GeoLite2-City-Test.mmdb`
    mock_client = mocker.patch("fastapi.Request.client")
    mock_client.host = "216.160.83.56"

    expected_log_data: dict[str, Any] = {
        "name": "web.suggest.request",
        "sensitive": True,
        "errno": 0,
        "time": "1998-03-31T00:00:00",
        "path": "/api/v1/suggest",
        "method": "GET",
        "query": "nope",
        "code": 200,
        "rid": "1b11844c52b34c33a6ad54b7bc2eb7c7",
        "session_id": "deadbeef-0000-1111-2222-333344445555",
        "sequence_no": 0,
        "client_variants": "foo,bar",
        "requested_providers": "pro,vider",
        "country": "US",
        "region": "WA",
        "city": "Milton",
        "dma": 819,
        "browser": "Firefox(103.0)",
        "os_family": "macos",
        "form_factor": "desktop",
    }

    client.get(
        f"{expected_log_data['path']}?q={expected_log_data['query']}"
        f"&sid={expected_log_data['session_id']}"
        f"&seq={expected_log_data['sequence_no']}"
        f"&client_variants={expected_log_data['client_variants']}"
        f"&providers={expected_log_data['requested_providers']}",
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 11.2; rv:85.0) "
                "Gecko/20100101 Firefox/103.0"
            ),
            "x-request-id": "1b11844c52b34c33a6ad54b7bc2eb7c7",
        },
    )

    records = filter_caplog(caplog.records, "web.suggest.request")
    assert len(records) == 1

    record = records[0]
    log_data: dict[str, Any] = {
        "name": record.name,
        "sensitive": record.__dict__["sensitive"],
        "errno": record.__dict__["errno"],
        "time": record.__dict__["time"],
        "path": record.__dict__["path"],
        "method": record.__dict__["method"],
        "query": record.__dict__["query"],
        "code": record.__dict__["code"],
        "rid": record.__dict__["rid"],
        "session_id": record.__dict__["session_id"],
        "sequence_no": record.__dict__["sequence_no"],
        "client_variants": record.__dict__["client_variants"],
        "requested_providers": record.__dict__["requested_providers"],
        "country": record.__dict__["country"],
        "region": record.__dict__["region"],
        "city": record.__dict__["city"],
        "dma": record.__dict__["dma"],
        "browser": record.__dict__["browser"],
        "os_family": record.__dict__["os_family"],
        "form_factor": record.__dict__["form_factor"],
    }
    assert log_data == expected_log_data


def test_suggest_with_invalid_geolocation_ip(
    mocker: MockerFixture,
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
    client: TestClient,
) -> None:
    """Test that a warning message is logged if geolocation data is invalid"""
    mock_client = mocker.patch("fastapi.Request.client")
    mock_client.host = "invalid-ip"

    client.get("/api/v1/suggest?q=nope")

    records = filter_caplog(caplog.records, "merino.middleware.geolocation")

    assert len(records) == 1
    assert records[0].message == "Invalid IP address for geolocation parsing"
