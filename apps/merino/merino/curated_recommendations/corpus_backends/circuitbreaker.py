"""This module defines all the circuit breakers for Curated Recommendations.

This module is separate from the apps/merino/merino/governance/circuitbreakers.py file due
to the application startup chain and curated recommendations being outside of
the "providers" pattern.
"""

from circuitbreaker import CircuitBreaker

from merino.configs import settings
from merino.curated_recommendations.corpus_backends.utils import CorpusGraphQLError
from merino.exceptions import BackendError
from httpx import HTTPError


async def curated_recommendations_circuitbreaker(*args, **kwargs) -> None:
    """Raise a generic BackendError while the circuit breaker is open."""
    raise BackendError("Corpus backend circuitbreaker")


class CuratedRecommendationsCircuitBreaker(CircuitBreaker):
    """Circuit breaker for the Curated Recommendations backends.

    this circuit breaker is intended to avoid a thundering herd problem
    when merino deploys - which doubles the pod count, all of which exist
    in a cold-start/empty cache state.

    this decorator sits between two other decorators on the `fetch` functions
    of any corpus backend (currently only sections). the
    decorator chain (first applied to last applied is):

    1. @retry - decorates with retry logic, only final result of final
      attempt of the wrapped fetch function is returned.

    2. { this decorator } - will return the FALLBACK_FUNCTION value for the
      given timeout if the final result of @retry above fails with an
      HTTPError or a CorpusGraphQLError. FALLBACK_FUNCTION must raise in
      order to tell the @stale_while_revalidate decorator below to return
      stale cache values (if present).

    3. @stale_while_revalidate - adds a check for in-memory, (ideally)
      non-expired cache value prior to calling the wrapped fetch function.
    """

    FAILURE_THRESHOLD = (
        settings.curated_recommendations.corpus_api.circuit_breaker_failure_threshold
    )
    RECOVERY_TIMEOUT = (
        settings.curated_recommendations.corpus_api.circuit_breaker_recover_timeout_sec
    )

    # Decorated fetch call should be circruit broken for the below API-related errors:
    EXPECTED_EXCEPTION = (HTTPError, CorpusGraphQLError)
    FALLBACK_FUNCTION = curated_recommendations_circuitbreaker
