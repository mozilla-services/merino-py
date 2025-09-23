"""FlightAware Integration"""

import aiodogstatsd
from fastapi import HTTPException
from merino.providers.suggest.base import BaseProvider, SuggestionRequest
from merino.providers.suggest.flightaware.backends.protocol import FlightBackendProtocol


class Provider(BaseProvider):
    """Suggestion provider for flight aware"""

    backend: FlightBackendProtocol
    metrics_client: aiodogstatsd.Client
    score: float

    def __init__(
        self,
        backend: FlightBackendProtocol,
        name: str,
        metrics_client: aiodogstatsd.Client,
        query_timeout_sec: float,
        score: float,
        enabled_by_default: bool = False,
    ):
        self.backend = backend
        self.metrics_client = metrics_client
        self.score = score
        self._name = name
        self._query_timeout_sec = query_timeout_sec
        self._enabled_by_default = enabled_by_default
        super().__init__()

    async def initialize(self) -> None:
        """Initialize the provider."""
        # TODO

    def validate(self, srequest: SuggestionRequest) -> None:
        """Validate the suggestion request."""
        if not srequest.query:
            raise HTTPException(
                status_code=400,
                detail="Invalid query parameters: `q` is missing",
            )

    async def query(self, request: SuggestionRequest):
        """Retrieve flight suggestions"""
        return []
