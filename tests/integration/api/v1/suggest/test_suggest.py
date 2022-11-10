# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Integration tests for the Merino v1 suggest API endpoint."""

import logging

import pytest
from fastapi.testclient import TestClient
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


def test_suggest_request_logs_contain_required_info(
    mocker: MockerFixture,
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
    client: TestClient,
) -> None:

    caplog.set_level(logging.INFO)

    # The IP address is taken from `GeoLite2-City-Test.mmdb`
    mock_client = mocker.patch("fastapi.Request.client")
    mock_client.host = "216.160.83.56"

    query = "nope"
    sid = "deadbeef-0000-1111-2222-333344445555"
    seq = 0
    client_variants = "foo,bar"
    providers = "pro,vider"
    root_path = "/api/v1/suggest"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 11.2;"
            " rv:85.0) Gecko/20100101 Firefox/103.0"
        )
    }
    client.get(
        f"{root_path}?q={query}&sid={sid}&seq={seq}"
        f"&client_variants={client_variants}&providers={providers}",
        headers=headers,
    )

    records = filter_caplog(caplog.records, "web.suggest.request")

    assert len(records) == 1

    record = records[0]

    assert record.name == "web.suggest.request"
    assert record.__dict__["sensitive"] is True
    assert record.__dict__["path"] == root_path
    assert record.__dict__["session_id"] == sid
    assert record.__dict__["sequence_no"] == seq
    assert record.__dict__["query"] == query
    assert record.__dict__["client_variants"] == client_variants
    assert record.__dict__["requested_providers"] == providers
    assert record.__dict__["browser"] == "Firefox(103.0)"
    assert record.__dict__["os_family"] == "macos"
    assert record.__dict__["form_factor"] == "desktop"
    assert record.__dict__["country"] == "US"
    assert record.__dict__["region"] == "WA"
    assert record.__dict__["city"] == "Milton"
    assert record.__dict__["dma"] == 819


def test_geolocation_with_invalid_ip(
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
