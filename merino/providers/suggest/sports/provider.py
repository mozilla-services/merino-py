"""This file declares the web API for the component. This is what gets called
by Merino, when we get a request to process.

"""

import logging

import aiodogstatsd
from pydantic import HttpUrl

from merino.providers.suggest.base import (
    BaseProvider,
    BaseSuggestion,
    CustomDetails,
    SuggestionRequest,
)
from merino.providers.suggest.base import Category
from merino.providers.suggest.sports import (
    LOGGING_TAG,
    BASE_SUGGEST_SCORE,
    PROVIDER_ID,
    IGNORED_SUGGESTION_URL,
)
from merino.providers.suggest.sports.backends.sportsdata.protocol import (
    SportEventDetails,
)
from merino.providers.suggest.sports.backends.sportsdata.backend import (
    SportsDataBackend,
    SportSummary,
)
from merino.providers.suggest.sports.backends.sportsdata.common.error import (
    SportsDataError,
)
from merino.providers.suggest.sports.backends.sportsdata.common.sports import TEAM_NAMES


class SportsDataProvider(BaseProvider):
    """This is the workhorse that provides responses to the request. We need
    to override any of the SportsDataProvider(BaseProvider) methods we want to
    customize.

    See the base class for additional functions

    """

    backend: SportsDataBackend | None
    metrics_client: aiodogstatsd.Client
    url: HttpUrl
    enabled_by_default: bool
    trigger_words: list[str]
    score: float

    def __init__(
        self,
        metrics_client: aiodogstatsd.Client,
        backend: SportsDataBackend,
        name: str = PROVIDER_ID,
        enabled_by_default: bool = False,
        trigger_words: list[str] = [],
        score: float = BASE_SUGGEST_SCORE,
        *args,
        **kwargs,
    ):
        self.metrics_client = metrics_client
        self.backend = backend
        self._name = name
        self.url = HttpUrl(IGNORED_SUGGESTION_URL)
        self._enabled_by_default = enabled_by_default
        self.trigger_words = trigger_words + TEAM_NAMES
        self.score = score

    async def initialize(self) -> None:
        """Create connections, components and other actions needed when starting up"""
        logger = logging.getLogger(__name__)
        logger.info(f"{LOGGING_TAG} Starting sports...")
        try:
            if self.backend:
                await self.backend.startup()
        except (Exception, SportsDataError) as ex:
            logger.error(f"{LOGGING_TAG} Could not start sports backend: {ex}")
            self.backend = None

    async def query(self, sreq: SuggestionRequest) -> list[BaseSuggestion]:
        """Query elastic search with the provided user terms and return relevant sport event information."""
        logger = logging.getLogger(__name__)
        if not sreq.query:
            return []
        if not self.backend:
            logger.error(f"{LOGGING_TAG} Sports backend unavailable due to configuration error")
            return []
        self.metrics_client.increment("sports.suggestions.count")
        # Both query and build suggestion have the ability to differentiate
        # and collate by sport. Product and UI do not want that, so
        # we will always return only one sport.
        results = await self.backend.query(sreq.query, score=self.score, url=self.url)
        return list(
            filter(
                None,
                [
                    self.build_suggestion(
                        # If we are collating, this should be the sport group.
                        sport_name="all",
                        query=sreq.query,
                        # TODO: A future version might use the highest elastic search score as a
                        # factor to improve the overall score of this result (e.g. a returned
                        # suggestion might add `self.score + (.01 * score_adj)`) to heighten
                        # more relevant results, but it's unclear how to best approach that now.
                        # This should be the max es_score value returned to
                        # act as a general score adjustment for this suggestion
                        # score_adj=0,
                        events=results,
                    )
                ],
            )
        )

    def normalize_query(self, query: str) -> str:
        """Perform whatever steps are required to normalize the user provided query string"""
        query = super().normalize_query(query)

        # here, we test for the presence of at least one "trigger word". These can be
        # sport related words, or team names (Note, for Soccer, these can be city or locales
        # so we may wish to not trigger on those, but rely on other words.)
        #
        # We don't want to just filter the query based on those words, because the query
        # may contain searchable terms that are not query words.
        if any(map(lambda w: w.lower() in self.trigger_words, query.split())):
            return query
        return ""

    def validate(self, srequest: SuggestionRequest) -> None:
        """Validate the incoming request"""
        return super().validate(srequest)

    def build_suggestion(
        self,
        sport_name: str,
        query: str,
        events: list[SportSummary],
        # score_adj: float = 0,
    ) -> BaseSuggestion | None:
        """Build a base suggestion with the sport data results"""
        logger = logging.getLogger(__name__)
        # "All" returns all sport events that match the search criteria.
        # Further work would be required to return results collated to their
        # respective sports. Each would be returned based on the `SportSummary.sport`.
        if not events:
            return None
        if sport_name == "all":
            sport_name = "All Sport"
            details = SportEventDetails(events[0])
        else:
            # Return an error because we shouldn't currently be returning anything
            # other than "mixed" results.
            logger.warning(
                f"{LOGGING_TAG} Multiple Sports provided to build_suggestion: {query}: {sport_name}"
            )
            return None
        self.metrics_client.increment("sports.suggestions.result", tags={"sport": sport_name})
        return BaseSuggestion(
            title=f"{sport_name}",  # IGNORED
            url=HttpUrl(IGNORED_SUGGESTION_URL),  # IGNORED
            description=f"{sport_name} report for {query}",
            provider=PROVIDER_ID,
            is_sponsored=False,
            custom_details=CustomDetails(sports=details),
            categories=[Category.Sports],
            score=self.score,
        )
