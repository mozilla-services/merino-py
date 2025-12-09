# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the flightaware error module."""

from merino.providers.suggest.flightaware.backends.errors import (
    FlightawareError,
    FlightawareErrorMessages,
)
from merino.exceptions import BackendError


def test_format_message_populates_placeholders():
    """Ensure format_message correctly substitutes placeholders."""
    message = FlightawareErrorMessages.HTTP_UNEXPECTED_FLIGHT_DETAILS_RESPONSE.format_message(
        flight_num="UA123", status_code=400, reason="Bad Request"
    )
    assert message == "Flightware request error for flight details for UA123: 400 Bad Request"


def test_flightaware_error_inherits_backenderror_and_formats_message():
    """Ensure FlightawareError wraps the message correctly and inherits from BackendError."""
    err = FlightawareError(FlightawareErrorMessages.CACHE_WRITE_ERROR, flight_num="UA123")
    assert isinstance(err, FlightawareError)
    assert isinstance(err, BackendError)
    assert "Error while setting flight summaries for UA123" in str(err)


def test_unexpected_backend_error_message():
    """Ensure UNEXPECTED_BACKEND_ERROR message formats as expected."""
    msg = FlightawareErrorMessages.UNEXPECTED_BACKEND_ERROR.format_message(flight_num="UA123")
    assert msg == "Unexpected error occurred when requesting flight details for UA123"
