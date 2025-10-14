"""This file declares the web API for the component. This is what gets called
by Merino, when we get a request to process.

"""

import aiodogstatsd
from pydantic import HttpUrl

from merino.providers.suggest.base import (
    BaseProvider,
    BaseSuggestion,
    CustomDetails,
    SuggestionRequest,
)
from merino.providers.suggest.custom_details import SportDetails
from merino.providers.suggest.base import Category
from merino.providers.suggest.sports.backends.sportsdata.backend import (
    SportsDataBackend,
    SportSummary,
)


class SportsDataProvider(BaseProvider):
    """This is the workhorse that provides responses to the request. We need
    to override any of the SportsDataProvider(BaseProvider) methods we want to
    customize.

    See the base class for additional functions

    """

    backend: SportsDataBackend
    metrics_client: aiodogstatsd.Client
    url: HttpUrl
    enabled_by_default: bool

    def __init__(
        self,
        metrics_client: aiodogstatsd.Client,
        backend: SportsDataBackend,
        name: str = "SportsData",
        enabled_by_default: bool = False,
        *args,
        **kwargs,
    ):
        self.metrics_client = metrics_client
        self.backend = backend
        self._name = name
        self.url = HttpUrl("https://merino.services.mozilla.com/")
        self._enabled_by_default = enabled_by_default
        super().__init__()

    def initialize(self):
        """Create connections, components and other actions needed when starting up"""
        pass

    async def query(self, sreq: SuggestionRequest) -> list[BaseSuggestion]:
        """Query elastic search with the provided user terms and return relevant sport event information."""
        if self.enabled_by_default:
            self.metrics_client.increment("sports.suggestions.count")
            results = await self.backend.query(
                sreq.query, score=self.backend.base_score, url=self.url
            )
            return [
                self.build_suggestion(
                    sport_name=result["sport"],
                    query=sreq.query,
                    score_adj=result.get("score", 0),
                    events=[result["summary"]],
                )
                for result in results
            ]
        return []

    def normalize_query(self, query: str) -> str:
        """Perform whatever steps are required to normalize the user provided query string"""
        return super().normalize_query(query)

    def validate(self, srequest: SuggestionRequest) -> None:
        """Validate the incoming request"""
        return super().validate(srequest)

    def build_suggestion(
        self,
        sport_name: str,
        query: str,
        events: list[SportSummary],
        score_adj: float = 0,
    ) -> BaseSuggestion:
        """Build a base suggestion with the sport data results"""
        if sport_name == "all":
            sport_name = "All Sport"
        return BaseSuggestion(
            title=f"{sport_name}",  # IGNORED
            url=HttpUrl("https://SportsData.io"),  # IGNORED
            description=f"{sport_name} report for {query}",
            provider="sportsdata_io",
            is_sponsored=False,
            custom_details=CustomDetails(sports=SportDetails(values=events)),
            categories=[Category.Sports],
            score=self.backend.base_score + score_adj,
        )
