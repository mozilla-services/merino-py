"""Yelp Integration"""

import aiodogstatsd
from fastapi import HTTPException
from pydantic import HttpUrl

from merino.providers.suggest.base import (
    BaseProvider,
    SuggestionRequest,
    BaseSuggestion,
)
from merino.providers.suggest.custom_details import CustomDetails, YelpDetails
from merino.providers.suggest.yelp.backends.keyword_mapping import LOCATION_KEYWORDS
from merino.providers.suggest.yelp.backends.protocol import (
    YelpBackendProtocol,
    YelpBusinessDetails,
)


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
        self.provider_id = name
        self._query_timeout_sec = query_timeout_sec
        self._enabled_by_default = enabled_by_default
        self.url = HttpUrl("https://merino.services.mozilla.com/")
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

        geolocation = srequest.geolocation
        location = geolocation.city if geolocation else None
        search_term = srequest.query.strip() if srequest.query else ""

        if not search_term or not location:
            raise HTTPException(
                status_code=400,
                detail="Valid query and location are required for Yelp suggestions",
            )

    async def query(self, request: SuggestionRequest):
        """Retrieve yelp suggestions"""
        geolocation = request.geolocation
        search_term = request.query.strip()

        yelp_business = await self.backend.get_business(search_term, geolocation)

        if yelp_business is not None:
            suggestions = [self.build_suggestion(yelp_business)]
            self.metrics_client.increment("yelp.suggestions.count", value=len(suggestions))
            return suggestions

        self.metrics_client.increment("yelp.suggestions.count", value=0)
        return []

    def build_suggestion(self, data: dict) -> BaseSuggestion | None:
        """Build the suggestion with custom yelp details."""
        values = [YelpBusinessDetails(**data)]
        custom_details = CustomDetails(yelp=YelpDetails(values=values))
        return BaseSuggestion(
            title="Yelp Suggestion",
            url=self.url,
            provider=self.name,
            is_sponsored=False,
            score=0.26,  # need to confirm value
            custom_details=custom_details,
        )

    def normalize_query(self, query: str) -> str:
        """Check whether the query ends in a location phrase
        that matches any in LOCATION_KEYWORDS.
        If so, the location phrase is the removed from the query and stripped of whitespace.
        """
        stripped = query.casefold().strip()

        # If it ends with a location keyword, strip it
        for loc_kw in LOCATION_KEYWORDS:
            if stripped.endswith(loc_kw):
                stripped = stripped.removesuffix(loc_kw).rstrip()
                break  # only strip once

        return stripped
