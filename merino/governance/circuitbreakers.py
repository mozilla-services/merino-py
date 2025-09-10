"""This module defines all the circuit breakers for Merino.


Circuit breakers can be used to monitor the "integration points" and react to
integration anomalies in Merino. External integrations (e.g. calling an external API endpoint)
and cloud dependencies (e.g. a database or a cache) are good candidates to be put
behind circuit breakers to guard Merino against integration interruptions.

To better manage circuit breakers for Merino, new breakers can be defined in this module.
Each breaker can be defined as follows:
  - Create a subclass of `CircuitBreaker` with the following class constants:
    - `FAILURE_THRESHOLD` {int}: A failure threshold for the breaker, when the failure count
      is greater or equal to it, the breaker state will transition from `closed` to `open`.
    - `RECOVERY_TIMEOUT` {int}: The recovery timeout in seconds for an opened breaker. During
      this window, all the subsequent calls to your integration point will be ignored and a
      `circuitbreaker.CircuitBreakerError` will be raised.
    - `EXPECTED_EXCEPTION` [{exception} | iter(exceptions)]: The expected exception(s) that
      the breaker cares about. Only these specific exception(s) will be listened and update
      the state of the breaker.
    - `FALLBACK_FUNCTION` {callable}: Optionally, a fallback function (or async function) can
      be called instead when the breaker is open. If this is specified, the
      `circuitbreaker.CircuitBreakerError` will no longer be raised as mentioned above.
  - You can create an instance of this circuit breaker class and attach it to a function
    or an async function, i.e. the integration point, as a new circuit breaker. Make sure
    you specify `name` in the constructor, this will be the ID of this breaker which can
    be used for monitoring later.
"""

from circuitbreaker import CircuitBreaker

from merino.configs import settings
from merino.exceptions import BackendError
from merino.providers.suggest.weather.backends.accuweather.errors import AccuweatherError
from merino.providers.suggest.base import BaseSuggestion


async def _suggest_provider_fallback_fn(*args, **kwargs) -> list[BaseSuggestion]:
    """Define a fallback function that returns an empty list when the circuit breaker is open."""
    return []


class WeatherCircuitBreaker(CircuitBreaker):
    """Circuit Breaker for the weather provider."""

    FAILURE_THRESHOLD = settings.providers.accuweather.circuit_breaker_failure_threshold
    RECOVERY_TIMEOUT = settings.providers.accuweather.circuit_breaker_recover_timeout_sec
    # This breaker only cares about these two errors, which would cover both Redis errors
    # and AccuWeather API errors.
    EXPECTED_EXCEPTION = (AccuweatherError, BackendError)
    # When the breaker is open, use this to simply return an empty suggestion list to the caller.
    FALLBACK_FUNCTION = _suggest_provider_fallback_fn


class GoogleSuggestCircuitBreaker(CircuitBreaker):
    """Circuit Breader for the Google Suggest provider."""

    FAILURE_THRESHOLD = settings.providers.google_suggest.circuit_breaker_failure_threshold
    RECOVERY_TIMEOUT = settings.providers.google_suggest.circuit_breaker_recover_timeout_sec
    # This breaker only cares about `BackendError` that could get raised for any
    # HTTP request failures to the Google Suggest endpoint
    EXPECTED_EXCEPTION = (BackendError,)
    # When the breaker is open, use this to simply return an empty suggestion list to the caller.
    FALLBACK_FUNCTION = _suggest_provider_fallback_fn
