# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the middleware geolocation module."""

import pytest
from pytest import LogCaptureFixture
from pytest_mock import MockerFixture
from starlette.types import ASGIApp, Receive, Scope, Send

from merino.middleware import ScopeKey
from merino.middleware.geolocation import (
    GeolocationMiddleware,
    Location,
    Coordinates,
)


@pytest.fixture(name="geolocation_middleware")
def fixture_geolocation_middleware(mocker: MockerFixture) -> GeolocationMiddleware:
    """Create a GeolocationMiddleware object for test."""
    asgiapp_mock = mocker.AsyncMock(spec=ASGIApp)
    return GeolocationMiddleware(asgiapp_mock)


# The first two IP addresses are taken from `GeoLite2-City-Test.mmdb`
@pytest.mark.parametrize(
    ["expected_location", "client_ip_and_port"],
    [
        (
            Location(
                country="US",
                country_name="United States",
                regions=["WA"],
                region_names=["Washington"],
                city="Milton",
                dma=819,
                postal_code="98354",
                coordinates=Coordinates(latitude=47.2513, longitude=-122.3149, radius=22),
                city_names={"en": "Milton", "ru": "Мильтон"},
            ),
            ["216.160.83.56", 50000],
        ),
        (
            Location(
                country="GB",
                country_name="United Kingdom",
                regions=["WBK", "ENG"],
                region_names=["West Berkshire", "England"],
                city="Boxford",
                postal_code="OX1",
                coordinates=Coordinates(latitude=51.75, longitude=-1.25, radius=100),
                city_names={"en": "Boxford"},
            ),
            ["2.125.160.216", 50000],
        ),
        (
            Location(),
            ["127.0.0.1", 50000],
        ),
    ],
)
@pytest.mark.asyncio
async def test_geolocation_address_found(
    caplog: LogCaptureFixture,
    geolocation_middleware: GeolocationMiddleware,
    scope: Scope,
    receive_mock: Receive,
    send_mock: Send,
    expected_location: Location,
    client_ip_and_port: list,
) -> None:
    """Test the proper assignment of Location properties given a request IP address."""
    scope["client"] = client_ip_and_port

    await geolocation_middleware(scope, receive_mock, send_mock)

    assert scope[ScopeKey.GEOLOCATION] == expected_location
    assert len(caplog.messages) == 0


@pytest.mark.asyncio
async def test_geolocation_address_not_found(
    caplog: LogCaptureFixture,
    geolocation_middleware: GeolocationMiddleware,
    scope: Scope,
    receive_mock: Receive,
    send_mock: Send,
) -> None:
    """Test that no assignment of Location properties takes place, given a request
    with an unrecognised IP address.
    """
    expected_location: Location = Location()
    scope["client"] = ["255.255.255.255", 50000]  # IP and port

    await geolocation_middleware(scope, receive_mock, send_mock)

    assert scope[ScopeKey.GEOLOCATION] == expected_location
    assert len(caplog.messages) == 0


@pytest.mark.asyncio
async def test_geolocation_client_ip_override(
    mocker: MockerFixture,
    caplog: LogCaptureFixture,
    geolocation_middleware: GeolocationMiddleware,
    scope: Scope,
    receive_mock: Receive,
    send_mock: Send,
) -> None:
    """Test that the CLIENT_IP_OVERRIDE environment variable will take precedence over
    request IP assignment.
    """
    expected_location: Location = Location(
        country="US",
        country_name="United States",
        regions=["WA"],
        region_names=["Washington"],
        city="Milton",
        dma=819,
        postal_code="98354",
        coordinates=Coordinates(latitude=47.2513, longitude=-122.3149, radius=22),
        city_names={"en": "Milton", "ru": "Мильтон"},
    )
    mocker.patch("merino.middleware.geolocation.CLIENT_IP_OVERRIDE", "216.160.83.56")

    await geolocation_middleware(scope, receive_mock, send_mock)

    assert scope[ScopeKey.GEOLOCATION] == expected_location
    assert len(caplog.messages) == 0


@pytest.mark.parametrize(
    "client_ip_and_port",
    [None, [None, 50000], ["", 50000], ["invalid-ip", 50000]],
)
@pytest.mark.asyncio
async def test_geolocation_invalid_address(
    caplog: LogCaptureFixture,
    geolocation_middleware: GeolocationMiddleware,
    scope: Scope,
    receive_mock: Receive,
    send_mock: Send,
    client_ip_and_port: list,
) -> None:
    """Test that a warning is logged and no assignment of Location properties takes
    place, given a request with an unexpected IP addresses.
    """
    expected_location: Location = Location()
    scope["client"] = client_ip_and_port

    await geolocation_middleware(scope, receive_mock, send_mock)

    assert scope[ScopeKey.GEOLOCATION] == expected_location
    assert len(caplog.messages) == 1
    assert caplog.messages[0] == "Invalid IP address for geolocation parsing"


@pytest.mark.asyncio
async def test_geolocation_invalid_scope_type(
    caplog: LogCaptureFixture,
    geolocation_middleware: GeolocationMiddleware,
    receive_mock: Receive,
    send_mock: Send,
) -> None:
    """Test that no action, Location assignment or logging, takes place for an
    unexpected Scope type.
    """
    scope: Scope = {"type": "not-http"}

    await geolocation_middleware(scope, receive_mock, send_mock)

    assert ScopeKey.GEOLOCATION not in scope
    assert len(caplog.messages) == 0
