import pytest
from fastapi.testclient import TestClient

from merino.main import app
from merino.providers import get_providers
from tests.web.util import get_providers as override_dependency

client = TestClient(app)
app.dependency_overrides[get_providers] = override_dependency


# The first two IP addresses are taken from `GeoLite2-City-Test.mmdb`
@pytest.mark.parametrize(
    "ip,expected_country,expected_region,expected_city,expected_dma",
    [
        ("216.160.83.56", "US", "WA", "Milton", 819),
        ("2.125.160.216", "GB", "ENG", "Boxford", None),
        ("127.0.0.1", None, None, None, None),
    ],
)
def test_geolocation(
    mocker, caplog, ip, expected_country, expected_region, expected_city, expected_dma
):
    import logging

    caplog.set_level(logging.INFO)

    mock_client = mocker.patch("fastapi.Request.client")
    mock_client.host = ip

    client.get("/api/v1/suggest?q=nope")

    assert len(caplog.records) == 1

    record = caplog.records[0]

    assert record.country == expected_country
    assert record.region == expected_region
    assert record.city == expected_city
    assert record.dma == expected_dma


def test_geolocation_with_invalid_ip(mocker, caplog):
    import logging

    caplog.set_level(logging.WARNING)

    mock_client = mocker.patch("fastapi.Request.client")
    mock_client.host = "invalid-ip"

    client.get("/api/v1/suggest?q=nope")

    assert len(caplog.records) == 1
    assert caplog.messages[0] == "Invalid IP address for geolocation parsing"
