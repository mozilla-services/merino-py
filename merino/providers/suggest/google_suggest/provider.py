"""Suggest provider for Google Suggest."""

import logging

import aiodogstatsd

from typing import cast

from fastapi import HTTPException
from pydantic import HttpUrl

from merino.governance.circuitbreakers import GoogleSuggestCircuitBreaker
from merino.providers.suggest.base import BaseProvider, BaseSuggestion, SuggestionRequest
from merino.providers.suggest.custom_details import CustomDetails, GoogleSuggestDetails
from merino.providers.suggest.google_suggest.backends.google_suggest import GoogleSuggestBackend
from merino.providers.suggest.google_suggest.backends.protocol import (
    GoogleSuggestResponse,
    SuggestRequest,
)


logger = logging.getLogger(__name__)


class Provider(BaseProvider):
    """Suggestion provider for Google Suggest."""

    backend: GoogleSuggestBackend
    metrics_client: aiodogstatsd.Client
    score: float
    # A dummy URL pointing to Merino itself
    url: HttpUrl

    def __init__(
        self,
        backend: GoogleSuggestBackend,
        score: float,
        name: str,
        enabled_by_default: bool = False,
    ) -> None:
        self.backend = backend
        self.score = score
        self._name = name
        self._enabled_by_default = enabled_by_default
        self.url = HttpUrl("https://merino.services.mozilla.com/")

        super().__init__()

    async def initialize(self) -> None:
        """Initialize the provider."""
        pass

    def validate(self, srequest: SuggestionRequest) -> None:
        """Validate the suggestion request."""
        if srequest.google_suggest_params is None:
            logger.warning(
                "HTTP 400: invalid query parameters, `google_suggest_params` is missing"
            )
            raise HTTPException(
                status_code=400,
                detail="Invalid query parameters: `google_suggest_params` is missing",
            )

        if srequest.query == "":
            logger.warning("HTTP 400: invalid query parameters, `q` should not be empty")
            raise HTTPException(
                status_code=400,
                detail="Invalid query parameters: `q` should not be empty",
            )

    @GoogleSuggestCircuitBreaker(name="google_suggest")  # Expect `BackendError`
    async def query(self, srequest: SuggestionRequest) -> list[BaseSuggestion]:
        """Provide Google Suggest suggestions.

        All the `BackendError` errors, raised from the frontend, are intentionally
        unhandled here to drive the circuit breaker. Those exceptions will eventually
        be propagated to the provider consumer (i.e. the API handler) and be handled
        there.
        """
        suggestions: GoogleSuggestResponse = await self.backend.fetch(
            SuggestRequest(
                query=srequest.query,
                params=cast(str, srequest.google_suggest_params),
            )
        )

        return [
            BaseSuggestion(
                title="Google Suggest",
                url=self.url,
                provider=self.name,
                is_sponsored=False,
                score=self.score,
                custom_details=CustomDetails(
                    google_suggest=GoogleSuggestDetails(suggestions=suggestions)
                ),
            )
        ]

    async def shutdown(self) -> None:
        """Shut down the provider."""
        await self.backend.shutdown()
