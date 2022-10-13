# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from unittest import mock
from unittest.mock import AsyncMock, Mock

import pytest
from pytest import LogCaptureFixture
from starlette.types import ASGIApp, Receive, Scope, Send

from merino.middleware.geolocation import GeolocationMiddleware, Location


@pytest.fixture(name="geolocation_middleware")
def fixture_geolocation_middleware() -> GeolocationMiddleware:
    """Creates a GeolocationMiddleware object for test"""
    asgiapp_mock = AsyncMock(spec=ASGIApp)
    return GeolocationMiddleware(asgiapp_mock)


@pytest.fixture(name="scope")
def fixture_scope() -> Scope:
    """Creates a Scope object for test"""
    scope: Scope = {"type": "http"}
    return scope


@pytest.fixture(name="receive_mock")
def fixture_receive_mock() -> Receive:
    """Creates a Receive mock object for test"""
    return Mock()


@pytest.fixture(name="send_mock")
def fixture_send_mock() -> Send:
    """Creates a Send mock object for test"""
    return Mock()


# The first two IP addresses are taken from `GeoLite2-City-Test.mmdb`
@pytest.mark.parametrize(
    "expected_location, client_ip_and_port",
    [
        (
            Location(
                country="US", region="WA", city="Milton", dma=819, postal_code="98354"
            ),
            ["216.160.83.56", 50000],
        ),
        (
            Location(country="GB", region="ENG", city="Boxford", postal_code="OX1"),
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
    """
    Test the proper assignment of Location properties given a request IP address.
    """
    scope["client"] = client_ip_and_port

    await geolocation_middleware(scope, receive_mock, send_mock)

    assert scope["merino_geolocation"] == expected_location
    assert len(caplog.messages) == 0


@pytest.mark.asyncio
async def test_geolocation_address_not_found(
    caplog: LogCaptureFixture,
    geolocation_middleware: GeolocationMiddleware,
    scope: Scope,
    receive_mock: Receive,
    send_mock: Send,
) -> None:
    """
    Test that no assignment of Location properties takes place, given a request with an
    unrecognised IP address.
    """
    expected_location: Location = Location()
    scope["client"] = ["255.255.255.255", 50000]  # IP and port

    await geolocation_middleware(scope, receive_mock, send_mock)

    assert scope["merino_geolocation"] == expected_location
    assert len(caplog.messages) == 0


@pytest.mark.asyncio
async def test_geolocation_client_ip_override(
    caplog: LogCaptureFixture,
    geolocation_middleware: GeolocationMiddleware,
    scope: Scope,
    receive_mock: Receive,
    send_mock: Send,
) -> None:
    """
    Test that the CLIENT_IP_OVERRIDE environment variable will take precedence over
    request IP assignment.
    """
    expected_location: Location = Location(
        country="US", region="WA", city="Milton", dma=819, postal_code="98354"
    )

    with mock.patch(
        "merino.middleware.geolocation.CLIENT_IP_OVERRIDE", "216.160.83.56"
    ):
        await geolocation_middleware(scope, receive_mock, send_mock)

    assert scope["merino_geolocation"] == expected_location
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
    """
    Test that a warning is logged and no assignment of Location properties takes place,
    given a request with an unexpected IP addresses.
    """
    expected_location: Location = Location()
    scope["client"] = client_ip_and_port

    await geolocation_middleware(scope, receive_mock, send_mock)

    assert scope["merino_geolocation"] == expected_location
    assert len(caplog.messages) == 1
    assert caplog.messages[0] == "Invalid IP address for geolocation parsing"


@pytest.mark.asyncio
async def test_geolocation_invalid_scope_type(
    caplog: LogCaptureFixture,
    geolocation_middleware: GeolocationMiddleware,
    receive_mock: Receive,
    send_mock: Send,
) -> None:
    """
    Test that no action, Location assignment or logging, takes place for an unexpected
    Scope type.
    """
    scope: Scope = {"type": "not-http"}

    await geolocation_middleware(scope, receive_mock, send_mock)

    assert "merino_geolocation" not in scope
    assert len(caplog.messages) == 0
