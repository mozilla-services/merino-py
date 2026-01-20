"""Errors module that maintains all the Massive specific error strings and the
MassiveError class to format and wrap them as a BackendError child object
"""

from enum import Enum
from merino.exceptions import BackendError


class MassiveErrorMessages(Enum):
    """Enum variables with string values representing error messages"""

    CACHE_WRITE_ERROR = "Something went wrong with storing to cache. Did not update cache."
    CACHE_READ_ERROR = "Failed to read from cache: {exception}"
    FAILED_FINANCE_REPORT = "Failed to fetch finance report: {exceptions}"
    HTTP_UNEXPECTED_RESPONSE = "Unexpected response for request: {req}"

    def format_message(self, **kwargs) -> str:
        """Format the enum string value with the passed in keyword arguments"""
        return self.value.format(**kwargs)


class MassiveError(BackendError):
    """Error during interaction with the Massive api. Inherits the BackendError parent
    class. On the provider level, this is caught as a BackendError type and logged.
    """

    def __init__(self, error_type: MassiveErrorMessages, **kwargs):
        # Use the `format_message` method to get the formatted error message
        message = error_type.format_message(**kwargs)
        super().__init__(message)
