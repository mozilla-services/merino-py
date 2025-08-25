"""Yelp Integration"""

import aiodogstatsd
from fastapi import HTTPException
from pydantic import HttpUrl

from merino.providers.suggest.base import BaseProvider, SuggestionRequest, BaseSuggestion
from merino.providers.suggest.custom_details import CustomDetails, YelpDetails
from merino.providers.suggest.yelp.backends.protocol import YelpBackendProtocol


class Provider(BaseProvider):
    """Suggestion provider for yelp"""

    backend: YelpBackendProtocol
    metrics_client: aiodogstatsd.Client
    score: float

    def __init__(
        self,
        backend: YelpBackendProtocol,
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
        """Retrieve yelp suggestions"""
        search_term = self.process_query()
        geolocation = request.geolocation
        location = geolocation.city if geolocation else None
        if not search_term or not location:
            return []

        if (yelp_business := await self.backend.get_businesses(search_term, location)) is not None:
            return [self.build_suggestion(yelp_business)]
        else:
            return []

    def build_suggestion(self, data: dict) -> BaseSuggestion | None:
        """Build the suggestion with custom yelp details."""
        url = data.pop("url")
        custom_details = CustomDetails(yelp=YelpDetails(**data))
        return BaseSuggestion(
            title="Yelp Suggestion",
            url=HttpUrl(url),
            provider=self.name,
            is_sponsored=False,
            score=0.26,  # need to confirm value
            custom_details=custom_details,
        )

    def process_query(self) -> str:
        """Stub placeholder until we finalize keywords."""
        return "coffee"
