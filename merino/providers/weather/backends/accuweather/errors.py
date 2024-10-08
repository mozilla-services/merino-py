"""Errors module that maintains all the accuweather specific error strings and the
AccuweatherError class to format and wrap them as a BackendError child object
"""

from enum import Enum
from merino.exceptions import BackendError


class AccuweatherErrorMessages(Enum):
    """Enum variables with string values representing error messages"""

    CACHE_WRITE_ERROR = "Something went wrong with storing to cache. Did not update cache."
    FAILED_WEATHER_REPORT = "Failed to fetch weather report: {exceptions}"
    HTTP_UNEXPECTED_LOCATION_RESPONSE = (
        "Unexpected location response from: {url_path}, city: {city}"
    )
    HTTP_UNEXPECTED_CURRENT_CONDITIONS_RESPONSE = (
        "Unexpected current conditions response, Url: {current_conditions_url}"
    )
    HTTP_UNEXPECTED_FORECAST_RESPONSE = "Unexpected forecast response, Url: {forecast_url}"
    HTTP_LOCATION_COMPLETION_ERROR = "Failed to get location completion from Accuweather, http error occurred. Url path: {url_path}, query: {search_term}, language: {language}"
    UNEXPECTED_GEOLOCATION_ERROR = "Unexpected error occurred when requesting location by geolocation from Accuweather: {exception_class_name}"
    UNEXPECTED_CURRENT_CONDITIONS_ERROR = "Unexpected error occurred when requesting current conditions from Accuweather: {exception_class_name}"
    UNEXPECTED_FORECAST_ERROR = "Unexpected error occurred when requesting forecast from Accuweather: {exception_class_name}"
    UNEXPECTED_LOCATION_COMPLETION_ERROR = "Unexpected error occurred when requesting location completion from Accuweather: {exception_class_name}"

    def format_message(self, **kwargs) -> str:
        """Format the enum string value with the passed in keyword arguments"""
        return self.value.format(**kwargs)


class AccuweatherError(BackendError):
    """Accuweather error type which inherits the BackendError parent class. On the provider
    level, this is caught as a BackendError type and logged.
    """

    def __init__(self, error_type: AccuweatherErrorMessages, **kwargs):
        # Use the `format_message` method to get the formatted error message
        message = error_type.format_message(**kwargs)
        super().__init__(message)
