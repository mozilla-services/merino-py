"""Handle incoming Sports related queries"""

from abc import abstractmethod
from dynaconf.base import LazySettings
from pydantic import HttpUrl
from typing import Protocol


from merino.providers.suggest.sports.backends.sportsdata.protocol import SportSummary
from merino.providers.suggest.sports.backends.sportsdata.common.elastic import (
    SportsDataStore,
)


class SportsDataProtocol(Protocol):
    """Protocol functions for Sports"""

    @abstractmethod
    async def shutdown(self) -> None:
        """Perform the shutdown steps"""


class SportsDataBackend(SportsDataProtocol):
    """Provide the methods specific to this provider for fulfilling the request"""

    data_store: SportsDataStore

    def __init__(
        self,
        store: SportsDataStore,
        settings: LazySettings,
        max_suggestions: int = 10,
        mix_sports: bool = True,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.data_store = store
        self.max_suggestions = max_suggestions
        self.mix_sports = mix_sports
        self.settings = settings

    async def query(
        self,
        query_string: str | None = None,
        language_code: str = "en",
        score: float = 0.5,
        url: HttpUrl | None = None,
    ) -> list[SportSummary]:
        """Query the data store for terms and return a list of potential sporting events relevant to those terms.

        This relies on Elastic's internal tokenizer and full text search to scan the list of "terms" for matching results.
        Note that we would want to use elastic's term score as a multiplier for the returned suggestion score, since it would
        indicate how likely that suggestion matched the provided query.
        """
        # break the description into words
        if query_string:
            # This will build a list of events by sport.
            # There is an outstanding question about whether we
            # should mix events for sports
            # (e.g. prior NHL, current MLB, future NFL)
            events = await self.data_store.search_events(
                q=query_string, language_code=language_code, mix_sports=self.mix_sports
            )
            suggestions: list[SportSummary] = []
            for sport, events in events.items():
                if len(suggestions) > self.max_suggestions:
                    break
                # TODO: collect the es_score from the events, calculate an average, and
                # apply that as an adjustment value to the returned score value.
                # Waiting for guidance about what ranges to have scores.
                suggestions.append(
                    SportSummary.from_events(
                        sport=sport,
                        events=events,
                    )
                )
            return suggestions
        return []

    async def shutdown(self) -> None:
        """Politely shut down the datastore"""
        await self.data_store.shutdown()

    async def startup(self) -> None:
        """Perform any initialization functions here.

        NOTE: The Merino elastic search account is READ_ONLY
        The Airflow elastic search is READ_WRITE.

        """
        await self.data_store.startup()
