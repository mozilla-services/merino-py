from typing import Any

from fastapi.testclient import TestClient

from merino.main import app
from merino.providers import get_providers
from tests.unit.web.util import filter_caplog
from tests.unit.web.util import get_providers as override_dependency

client = TestClient(app)
app.dependency_overrides[get_providers] = override_dependency


def test_geolocation(mocker: Any, caplog: Any) -> None:
    ip: str = "216.160.83.56"  # The IP address is taken from `GeoLite2-City-Test.mmdb`
    expected_country = "US"
    expected_region = "WA"
    expected_city = "Milton"
    expected_dma = 819
    expected_postal_code = "98354"

    mock_client = mocker.patch("fastapi.Request.client")
    mock_client.host = ip

    client.get("/api/v1/suggest?q=nope")

    records = filter_caplog(caplog.records, "web.suggest.request")

    assert len(records) == 1

    record = records[0]

    assert record.__dict__["country"] == expected_country
    assert record.__dict__["region"] == expected_region
    assert record.__dict__["city"] == expected_city
    assert record.__dict__["dma"] == expected_dma
    assert record.__dict__["postal_code"] == expected_postal_code


def test_geolocation_with_invalid_ip(mocker: Any, caplog: Any) -> None:
    mock_client = mocker.patch("fastapi.Request.client")
    mock_client.host = "invalid-ip"

    client.get("/api/v1/suggest?q=nope")

    records = filter_caplog(caplog.records, "merino.middleware.geolocation")

    assert len(records) == 1
    assert records[0].message == "Invalid IP address for geolocation parsing"
