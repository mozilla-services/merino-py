# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Integration tests for the Merino v1 suggest API endpoint."""

import logging

import aiodogstatsd
import pytest
from fastapi.testclient import TestClient
from freezegun import freeze_time
from pytest import LogCaptureFixture
from pytest_mock import MockerFixture

from merino.utils.log_data_creators import SuggestLogDataModel
from tests.integration.api.v1.fake_providers import FakeProviderFactory
from tests.integration.api.v1.types import Providers
from tests.types import FilterCaplogFixture


@pytest.fixture(name="providers")
def fixture_providers() -> Providers:
    """Define providers for this module which are injected automatically.

    Note: This fixture will be overridden if a test method has a
          'pytest.mark.parametrize' decorator with a 'providers' definition.
    """
    return {
        "sponsored": FakeProviderFactory.sponsored(enabled_by_default=True),
        "non-sponsored": FakeProviderFactory.nonsponsored(enabled_by_default=True),
    }


def test_suggest_sponsored(client: TestClient) -> None:
    """Test that the suggest endpoint response is as expected using a sponsored
    provider.
    """
    response = client.get("/api/v1/suggest?q=sponsored")
    assert response.status_code == 200

    result = response.json()
    assert len(result["suggestions"]) == 1
    assert result["suggestions"][0]["full_keyword"] == "sponsored"
    assert result["request_id"] is not None


def test_suggest_nonsponsored(client: TestClient) -> None:
    """Test that the suggest endpoint response is as expected using a non-sponsored
    provider.
    """
    response = client.get("/api/v1/suggest?q=nonsponsored")

    assert response.status_code == 200

    result = response.json()
    assert len(result["suggestions"]) == 1
    assert result["suggestions"][0]["full_keyword"] == "nonsponsored"
    assert result["request_id"] is not None


def test_no_suggestion(client: TestClient) -> None:
    """Test that the suggest endpoint response is as expected when no suggestions are
    returned from providers.
    """
    response = client.get("/api/v1/suggest?q=nope")
    assert response.status_code == 200
    assert len(response.json()["suggestions"]) == 0


@pytest.mark.parametrize("query", ["sponsored", "nonsponsored"])
def test_suggest_from_missing_providers(client: TestClient, query: str) -> None:
    """Despite the keyword being available for other providers, it should not return
    any suggestions if the requested provider does not exist.
    """
    response = client.get(f"/api/v1/suggest?q={query}&providers=nonexist")
    assert response.status_code == 200
    assert len(response.json()["suggestions"]) == 0


def test_no_query_string(client: TestClient) -> None:
    """Test that a status code of 400 is returned for suggest endpoint calls without
    a query string.
    """
    response = client.get("/api/v1/suggest")
    assert response.status_code == 400


def test_client_variants(client: TestClient) -> None:
    """Test that the suggest endpoint response is as expected when called with the
    client_variants parameter.
    """
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
    """Tests that the request logs for the 'suggest' endpoint contain the required
    extra data.
    """
    caplog.set_level(logging.INFO)

    # The IP address is taken from `GeoLite2-City-Test.mmdb`
    mock_client = mocker.patch("fastapi.Request.client")
    mock_client.host = "216.160.83.56"

    expected_log_data: SuggestLogDataModel = SuggestLogDataModel(
        sensitive=True,
        errno=0,
        time="1998-03-31T00:00:00",
        path="/api/v1/suggest",
        method="GET",
        query="nope",
        code=200,
        rid="1b11844c52b34c33a6ad54b7bc2eb7c7",
        session_id="deadbeef-0000-1111-2222-333344445555",
        sequence_no=0,
        client_variants="foo,bar",
        requested_providers="pro,vider",
        country="US",
        region="WA",
        city="Milton",
        dma=819,
        browser="Firefox(103.0)",
        os_family="macos",
        form_factor="desktop",
    )

    client.get(
        url=expected_log_data.path,
        params={
            "q": expected_log_data.query,
            "sid": expected_log_data.session_id,
            "seq": expected_log_data.sequence_no,
            "client_variants": expected_log_data.client_variants,
            "providers": expected_log_data.requested_providers,
        },
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
    log_data: SuggestLogDataModel = SuggestLogDataModel(
        sensitive=record.__dict__["sensitive"],
        errno=record.__dict__["errno"],
        time=record.__dict__["time"],
        path=record.__dict__["path"],
        method=record.__dict__["method"],
        query=record.__dict__["query"],
        code=record.__dict__["code"],
        rid=record.__dict__["rid"],
        session_id=record.__dict__["session_id"],
        sequence_no=record.__dict__["sequence_no"],
        client_variants=record.__dict__["client_variants"],
        requested_providers=record.__dict__["requested_providers"],
        country=record.__dict__["country"],
        region=record.__dict__["region"],
        city=record.__dict__["city"],
        dma=record.__dict__["dma"],
        browser=record.__dict__["browser"],
        os_family=record.__dict__["os_family"],
        form_factor=record.__dict__["form_factor"],
    )

    assert log_data == expected_log_data


def test_suggest_with_invalid_geolocation_ip(
    mocker: MockerFixture,
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
    client: TestClient,
) -> None:
    """Test that a warning message is logged if geolocation data is invalid."""
    mock_client = mocker.patch("fastapi.Request.client")
    mock_client.host = "invalid-ip"

    client.get("/api/v1/suggest?q=nope")

    records = filter_caplog(caplog.records, "merino.middleware.geolocation")

    assert len(records) == 1
    assert records[0].message == "Invalid IP address for geolocation parsing"


@pytest.mark.parametrize(
    ["url", "expected_metric_keys"],
    [
        (
            "/api/v1/suggest?q=none",
            [
                "providers.sponsored.query",
                "providers.non-sponsored.query",
                "suggestions-per.request",
                "suggestions-per.provider.sponsored",
                "suggestions-per.provider.non-sponsored",
                "get.api.v1.suggest.timing",
                "get.api.v1.suggest.status_codes.200",
                "response.status_codes.200",
            ],
        ),
        (
            "/api/v1/suggest",
            [
                "get.api.v1.suggest.timing",
                "get.api.v1.suggest.status_codes.400",
                "response.status_codes.400",
            ],
        ),
    ],
    ids=["status_code_200", "status_code_400"],
)
def test_suggest_metrics(
    mocker: MockerFixture,
    client: TestClient,
    url: str,
    expected_metric_keys: list[str],
) -> None:
    """Test that metrics are recorded for the 'suggest' endpoint
    (status codes: 200 & 400).
    """
    report = mocker.patch.object(aiodogstatsd.Client, "_report")

    client.get(url)

    # TODO: Remove reliance on internal details of aiodogstatsd
    metric_keys: list[str] = [call.args[0] for call in report.call_args_list]
    assert metric_keys == expected_metric_keys


@pytest.mark.parametrize("providers", [{"corrupt": FakeProviderFactory.corrupt()}])
def test_suggest_metrics_500(mocker: MockerFixture, client: TestClient) -> None:
    """Test that 500 status codes are recorded as metrics."""
    error_msg = "test"
    expected_metric_keys = [
        "providers.corrupted.query",
        "get.api.v1.suggest.timing",
        "get.api.v1.suggest.status_codes.500",
        "response.status_codes.500",
    ]

    report = mocker.patch.object(aiodogstatsd.Client, "_report")

    with pytest.raises(RuntimeError) as excinfo:
        client.get(f"/api/v1/suggest?q={error_msg}")

    # TODO: Remove reliance on internal details of aiodogstatsd
    metric_keys: list[str] = [call.args[0] for call in report.call_args_list]
    assert metric_keys == expected_metric_keys

    assert str(excinfo.value) == error_msg


@pytest.mark.parametrize(
    ["url", "expected_metric_keys", "expected_feature_flag_tags"],
    [
        (
            "/api/v1/suggest?q=none",
            [
                "providers.sponsored.query",
                "providers.non-sponsored.query",
                "suggestions-per.request",
                "suggestions-per.provider.sponsored",
                "suggestions-per.provider.non-sponsored",
                "get.api.v1.suggest.timing",
                "get.api.v1.suggest.status_codes.200",
                "response.status_codes.200",
            ],
            [],
        ),
        (
            "/api/v1/suggest",
            [
                "get.api.v1.suggest.timing",
                "get.api.v1.suggest.status_codes.400",
                "response.status_codes.400",
            ],
            [],
        ),
    ],
    ids=["200_with_feature_flags_tags", "400_no_tags"],
)
def test_suggest_feature_flags_tags_in_metrics(
    mocker: MockerFixture,
    client: TestClient,
    url: str,
    expected_metric_keys: list,
    expected_feature_flag_tags: list,
):
    """Test that feature flags are added for the 'suggest' endpoint
    (status codes: 200 & 400).
    """
    expected_tags_per_metric = {
        metric_key: expected_feature_flag_tags for metric_key in expected_metric_keys
    }

    report = mocker.patch.object(aiodogstatsd.Client, "_report")

    client.get(url)

    # TODO: Remove reliance on internal details of aiodogstatsd
    feature_flag_tags_per_metric = {
        call.args[0]: [
            tag for tag in call.args[3].keys() if tag.startswith("feature_flag.")
        ]
        for call in report.call_args_list
    }

    assert expected_tags_per_metric == feature_flag_tags_per_metric
