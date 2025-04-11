# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Integration tests for the Merino v1 suggest API endpoint."""

import logging
from datetime import datetime

import aiodogstatsd
import pytest
from fastapi.testclient import TestClient
from freezegun import freeze_time
from pytest import LogCaptureFixture
from pytest_mock import MockerFixture

from merino.configs import settings
from merino.utils.log_data_creators import SuggestLogDataModel
from tests.integration.api.v1.fake_providers import FakeProviderFactory
from tests.integration.api.v1.types import Providers
from tests.types import FilterCaplogFixture

# Defined in testing.toml under [testing.web.api.v1]
CLIENT_VARIANT_MAX = settings.web.api.v1.client_variant_max
QUERY_CHARACTER_MAX = settings.web.api.v1.query_character_max
CLIENT_VARIANT_CHARACTER_MAX = settings.web.api.v1.client_variant_character_max


@pytest.fixture(name="providers")
def fixture_providers() -> Providers:
    """Define providers for this module which are injected automatically.

    Note: This fixture will be overridden if a test method has a
          'pytest.mark.parametrize' decorator with a 'providers' definition.
    """
    return {
        "sponsored": FakeProviderFactory.sponsored(enabled_by_default=True),
        "non-sponsored": FakeProviderFactory.nonsponsored(enabled_by_default=True),
        "top_picks": FakeProviderFactory.sponsored(enabled_by_default=False),
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


def test_query_max_length(client: TestClient) -> None:
    """Test that the suggest endpoint query is limited by the defined query_max_length.
    While no result will return, this tests a matching string length up to max.
    Constant in configuration under [default | testing].web.api.v1.query_max_length.
    """
    query_string = "a" * QUERY_CHARACTER_MAX
    response = client.get(f"/api/v1/suggest?q={query_string}")
    assert response.status_code == 200
    assert len(response.json()["suggestions"]) == 0


def test_query_failure_exceeds_max_length(client: TestClient) -> None:
    """Test that the suggest endpoint query is limited by the defined query_max_length.
    This ensures a 400 code returns and the request fails.
    Constant in configuration under [default | testing].web.api.v1.query_max_length.
    """
    query_string = "a" * (QUERY_CHARACTER_MAX * 2)
    response = client.get(f"/api/v1/suggest?q={query_string}")
    assert response.status_code == 400


def test_suggest_duplicate_providers(client: TestClient) -> None:
    """Test to ensure that duplicated providers passed into the suggest endpoint do not
    result in a flood of responses that could result in Denial of Service. A duplicated
    provider name should not result in an additional lookup.
    """
    provider = ("sponsored," * 100).rstrip(",")
    response = client.get(f"/api/v1/suggest?q=sponsored&providers={provider}")
    assert response.status_code == 200
    assert len(response.json()["suggestions"]) == 1


@pytest.mark.parametrize("query", ["sponsored", "nonsponsored"])
def test_suggest_from_missing_providers(client: TestClient, query: str) -> None:
    """Despite the keyword being available for other providers, it should not return
    any suggestions if the requested provider does not exist.
    """
    response = client.get(f"/api/v1/suggest?q={query}&providers=nonexist")
    assert response.status_code == 200
    assert len(response.json()["suggestions"]) == 0


@pytest.mark.parametrize(
    "query",
    [
        "sponsored",
        "nonsponsored",
    ],
)
def test_suggest_default_wildcard_providers(client: TestClient, query: str) -> None:
    """Test that `default` wildcard provider parameter returns suggestions from default
    enabled providers.
    """
    response = client.get(f"/api/v1/suggest?q={query}&providers=default")
    assert response.status_code == 200
    assert len(response.json()["suggestions"]) == 1


@pytest.mark.parametrize(
    "query",
    [
        "sponsored",
    ],
)
def test_suggest_default_wildcard_providers_and_additional_provider(
    client: TestClient, query: str
) -> None:
    """Test that `default` wildcard provider parameter plus an added parameter
    for disabled provider returns suggestions from all passed in providers.
    """
    response = client.get(f"/api/v1/suggest?q={query}&providers=default,top_picks")
    assert response.status_code == 200
    assert len(response.json()["suggestions"]) == 2


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


def test_client_variants_duplicated_variant(client: TestClient) -> None:
    """Test that the suggest endpoint response only returns a single value for client_variant,
    limited by the CLIENT_VARIANT_MAX as the total possible recurrences of the value,
    even if the request is bombarded with an identical client_variant of the same name.
    """
    # 24 selected as it results in total string length of 96 characters.
    # ',' is inclusive, in addition to variant 'foo.'
    duplicated_client_variant = ("foo," * 24).rstrip(",")
    response = client.get(
        f"/api/v1/suggest?q=sponsored&client_variants={duplicated_client_variant}"
    )
    assert response.status_code == 200

    result = response.json()
    assert len(result["suggestions"]) == 1
    assert "foo" in result["client_variants"]
    assert ["foo"] == list(set(result["client_variants"]))
    assert len(result["client_variants"]) == CLIENT_VARIANT_MAX


def test_client_variants_several_duplicated_variants(client: TestClient) -> None:
    """Test that the suggest endpoint response only returns client_variants not exceeding
    the defined client_variant_max, not any trailing string values, even if the request
    is bombarded with identical client_variants of different names.
    """
    variants = ["foo", "bar", "baz", "fizz", "buzz"]
    # 2 multiplications of the variants plus the comma values result in
    # fewer than the defined maximum.
    duplicated_client_variants = ",".join([*variants * 2]).rstrip(",")
    response = client.get(
        f"/api/v1/suggest?q=sponsored&client_variants={duplicated_client_variants}"
    )
    assert response.status_code == 200

    result = response.json()
    assert len(result["suggestions"]) == 1
    # Both the client_variants and test data are converted to sets to check membership.
    assert [*variants] == result["client_variants"]
    assert len(result["client_variants"]) == CLIENT_VARIANT_MAX


def test_client_variants_return_minimum_variants(client: TestClient) -> None:
    """Test that the suggest endpoint restriction of CLIENT_VARIANT_MAX is met.
    Ensure that the response does not reflect back excessive client variants, nor trailing
    string values.
    """
    client_variants = ["foo", "bar", "baz", "fizz", "buzz", "foobar"]

    response = client.get(
        f"/api/v1/suggest?q=sponsored&client_variants={','.join(client_variants).rstrip(',')}"
    )
    assert response.status_code == 200

    result = response.json()
    assert len(result["suggestions"]) == 1
    # NOTE: Shorter value of 5 for client_variant_max used for testing.
    # See testing..web.api.v1.client_variant_max.
    # Prod value in default..web.api.v1.client_variant_max.
    assert len(result["client_variants"]) == CLIENT_VARIANT_MAX


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
        time=datetime(1998, 3, 31),
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
                ("providers.sponsored.query", None),
                ("providers.non-sponsored.query", None),
                ("suggestions-per.request", None),
                ("suggestions-per.provider.sponsored", None),
                ("suggestions-per.provider.non-sponsored", None),
                ("get.api.v1.suggest.timing", None),
                (
                    "get.api.v1.suggest.status_codes.200",
                    {"browser": "Firefox(103.0)", "form_factor": "desktop", "os_family": "macos"},
                ),
                (
                    "response.status_codes.200",
                    {"browser": "Firefox(103.0)", "form_factor": "desktop", "os_family": "macos"},
                ),
            ],
        ),
        (
            "/api/v1/suggest",
            [
                ("get.api.v1.suggest.timing", None),
                (
                    "get.api.v1.suggest.status_codes.400",
                    {"browser": "Firefox(103.0)", "form_factor": "desktop", "os_family": "macos"},
                ),
                (
                    "response.status_codes.400",
                    {"browser": "Firefox(103.0)", "form_factor": "desktop", "os_family": "macos"},
                ),
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

    client.get(
        url=url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 11.2; rv:85.0) "
                "Gecko/20100101 Firefox/103.0"
            ),
        },
    )

    # TODO: Remove reliance on internal details of aiodogstatsd
    metric_keys: list[tuple[str, dict]] = [
        (call.args[0], call.args[3]) for call in report.call_args_list
    ]
    assert metric_keys == expected_metric_keys
