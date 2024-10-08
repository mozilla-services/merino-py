"""TODO"""

from enum import Enum

from merino.exceptions import BackendError


class AccuweatherErrorMessages(Enum):
    """TODO"""

    CACHE_WRITE_ERROR = "Something went wrong with storing to cache. Did not update cache."
    FAILED_WEATHER_REPORT = "Failed to fetch weather report: {exceptions}"
    UNEXPECTED_LOCATION_RESPONSE = "Unexpected location response from: {url_path}, city: {city}"
    UNEXPECTED_GEOLOCATION_REQUEST_ERROR = "Unexpected error occurred when requesting location by geolocation from Accuweather: {exception_class_name}"
    UNEXPECTED_CURRENT_CONDITIONS_RESPONSE = (
        "Unexpected current conditions response, Url: {current_conditions_url}"
    )
    UNEXPECTED_CURRENT_CONDITIONS_REQUEST_ERROR = "Unexpected error occurred when requesting current conditions from Accuweather: {exception_class_name}"
    UNEXPECTED_FORECAST_RESPONSE = "Unexpected forecast response, Url: {forecast_url}"
    UNEXPECTED_FORECAST_REQUEST_ERROR = "Unexpected error occurred when requesting forecast from Accuweather: {exception_class_name}"
    FAILED_LOCATION_COMPLETION = "Failed to get location completion from Accuweather, http error occurred. Url path: {url_path}, query: {search_term}, language: {language}"
    UNEXPECTED_LOCATION_COMPLETION_REQUEST_ERROR = "Unexpected error occurred when requesting location completion from Accuweather: {exception_class_name}"

    def format_message(self, **kwargs) -> str:
        """TODO"""
        return self.value.format(**kwargs)


class AccuweatherError(BackendError):
    """Error during interaction with the AccuWeather API."""

    def __init__(self, error_type: AccuweatherErrorMessages, **kwargs):
        # Use the `format_message` method to get the formatted error message
        message = error_type.format_message(**kwargs)
        super().__init__(message)
