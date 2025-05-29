"""Errors module that maintains all the Polygon specific error strings and the
PolygonError class to format and wrap them as a BackendError child object
"""

from enum import Enum
from merino.exceptions import BackendError


class PolygonErrorMessages(Enum):
    """Enum variables with string values representing error messages"""

    CACHE_WRITE_ERROR = "Something went wrong with storing to cache. Did not update cache."
    CACHE_READ_ERROR = "Failed to read from cache: {exception}"
    FAILED_WEATHER_REPORT = "Failed to fetch weather report: {exceptions}"
    HTTP_UNEXPECTED_RESPONSE = "Unexpected response for request: {req}"

    def format_message(self, **kwargs) -> str:
        """Format the enum string value with the passed in keyword arguments"""
        return self.value.format(**kwargs)


class PolygonError(BackendError):
    """Error during interaction with the Polygon api. Inherits the BackendError parent
    class. On the provider level, this is caught as a BackendError type and logged.
    """

    def __init__(self, error_type: PolygonErrorMessages, **kwargs):
        # Use the `format_message` method to get the formatted error message
        message = error_type.format_message(**kwargs)
        super().__init__(message)
