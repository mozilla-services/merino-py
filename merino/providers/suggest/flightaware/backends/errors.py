"""Errors module that maintains all the flightaware specific error strings and the
FlightAwareError class to format and wrap them as a BackendError child object
"""

from enum import Enum
from merino.exceptions import BackendError


class FlightawareErrorMessages(Enum):
    """Enum variables with string values representing error messages"""

    CACHE_WRITE_ERROR = "Error while setting flight summaries for {flight_num}"
    CACHE_READ_ERROR = "Error while getting flight summaries for {flight_num}"
    CACHE_DATA_PARSING_ERROR = "Failed to parse cached data for {flight_num}"
    HTTP_UNEXPECTED_FLIGHT_DETAILS_RESPONSE = (
        "Flightware request error for flight details for {flight_num}: {status_code} {reason}"
    )
    UNEXPECTED_BACKEND_ERROR = (
        "Unexpected error occurred when requesting flight details for {flight_num}"
    )

    def format_message(self, **kwargs) -> str:
        """Format the enum string value with the passed in keyword arguments"""
        return self.value.format(**kwargs)


class FlightawareError(BackendError):
    """Error during interaction with the Flightaware api. Inherits the BackendError parent
    class. On the provider level, this is caught as a BackendError type and logged.
    """

    def __init__(self, error_type: FlightawareErrorMessages, **kwargs):
        # Use the `format_message` method to get the formatted error message
        message = error_type.format_message(**kwargs)
        super().__init__(message)
