"""Circuit breaker for the Wrexham widget's Redis reads.

This lives here rather than in `merino/governance/circuitbreakers.py` because that module
imports the suggest providers. The widget runtime mode doesn't load those, and importing them
from here causes a circular import at startup.
"""

from collections.abc import Callable, Coroutine
from typing import Any, ParamSpec, TypeVar, cast

from circuitbreaker import CircuitBreaker

from merino.configs import settings
from merino.exceptions import CacheAdapterError

P = ParamSpec("P")  # Parameters of the decorated function
R = TypeVar("R")  # Return type of the decorated function


class WrexhamCircuitBreaker(CircuitBreaker):
    """Circuit breaker for the Wrexham widget's Redis reads."""

    FAILURE_THRESHOLD = settings.widgets.providers.wrexham.circuit_breaker_failure_threshold
    RECOVERY_TIMEOUT = settings.widgets.providers.wrexham.circuit_breaker_recover_timeout_sec
    # Only Redis errors trip it. Missing data (e.g. the job hasn't written yet) doesn't.
    EXPECTED_EXCEPTION = CacheAdapterError
    # No fallback: while it's open, calls raise `CircuitBreakerError`, which the provider turns
    # into a 503.


def guarded_by(
    breaker: CircuitBreaker,
) -> Callable[[Callable[P, Coroutine[Any, Any, R]]], Callable[P, Coroutine[Any, Any, R]]]:
    """Return a decorator that puts an async function behind `breaker`.

    Use this instead of `@breaker` directly: `circuitbreaker` has no type hints, so editors
    can't tell the decorated function is still async. This keeps its signature and return type.
    """

    def decorate(
        function: Callable[P, Coroutine[Any, Any, R]],
    ) -> Callable[P, Coroutine[Any, Any, R]]:
        return cast(Callable[P, Coroutine[Any, Any, R]], breaker(function))

    return decorate
