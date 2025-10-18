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
from merino.providers.suggest.base import Category
from merino.providers.suggest.sports.backends.sportsdata.common.error import (
    SportsDataError,
)
from merino.providers.suggest.sports.backends.sportsdata.protocol import (
    SportEventDetails,
)
from merino.providers.suggest.sports.backends.sportsdata.backend import (
    SportsDataBackend,
    SportSummary,
)
from merino.providers.suggest.sports.backends.sportsdata.common.sports import TEAM_NAMES


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
    trigger_words: list[str]

    def __init__(
        self,
        metrics_client: aiodogstatsd.Client,
        backend: SportsDataBackend,
        name: str = "SportsData",
        enabled_by_default: bool = False,
        trigger_words: list[str] = [],
        *args,
        **kwargs,
    ):
        self.metrics_client = metrics_client
        self.backend = backend
        self._name = name
        self.url = HttpUrl("https://merino.services.mozilla.com/")
        self._enabled_by_default = enabled_by_default
        self.trigger_words = trigger_words + TEAM_NAMES
        # TODO: Add all teams, sports to trigger_words ?
        super().__init__()

    def initialize(self):
        """Create connections, components and other actions needed when starting up"""
        pass

    async def query(self, sreq: SuggestionRequest) -> list[BaseSuggestion]:
        """Query elastic search with the provided user terms and return relevant sport event information."""
        if self.enabled_by_default:
            # scan the query for trigger words.
            trigger = False
            for word in [word.lower().strip() for word in sreq.query.split(" ")]:
                # we're not using "in" because that may match partials in words. (e.g. "matchstick")
                trigger |= word in self.trigger_words
            if not trigger:
                return []

            self.metrics_client.increment("sports.suggestions.count")
            with self.metrics_client.timeit("sports.suggestion.query"):
                # Both query and build suggestion have the ability to differentiate
                # and collate by sport. Product and UI do not want that, so
                # we will always return only one sport.
                results = await self.backend.query(
                    sreq.query, score=self.backend.base_score, url=self.url
                )
                return [
                    self.build_suggestion(
                        # If we are collating, this should be the sport group.
                        sport_name="all",
                        query=sreq.query,
                        # This should be the max es_score value returned to
                        # act as a general score adjustment for this suggestion
                        score_adj=0,
                        events=results,
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
            details = SportEventDetails(events[0])
        else:
            # TODO, construct a collated detail set.
            raise SportsDataError("Multiple Sports Returned")
        self.metrics_client.increment("sports.suggestions.result", tags={"sport": sport_name})
        return BaseSuggestion(
            title=f"{sport_name}",  # IGNORED
            url=HttpUrl("https://SportsData.io"),  # IGNORED
            description=f"{sport_name} report for {query}",
            provider="sportsdata_io",
            is_sponsored=False,
            custom_details=CustomDetails(sports=details),
            categories=[Category.Sports],
            score=self.backend.base_score + score_adj,
        )
