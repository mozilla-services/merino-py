"""Handle incoming Sports related queries"""

from abc import abstractmethod
from dynaconf.base import LazySettings
from pydantic import HttpUrl
from typing import Protocol, cast

from merino.providers.suggest.sports.backends.sportsdata.protocol import SportSummary
from merino.providers.suggest.sports.backends.sportsdata.common.elastic import (
    SportsDataStore,
)


def str_to_list(source: str) -> list[str]:
    """Convert a comma delimited string into a list"""
    return [item.strip() for item in source.split(",")]


class SportsDataProtocol(Protocol):
    """Protocol functions for Sports"""

    @abstractmethod
    async def shutdown(self) -> None:
        """Perform the shutdown steps"""


class SportsDataBackend(SportsDataProtocol):
    """Provide the methods specific to this provider for fulfilling the request"""

    data_store: SportsDataStore
    base_score: float

    def __init__(self, settings: LazySettings, *args, **kwargs):
        super().__init__(*args, **kwargs)
        platform = settings.get("platform", "sports")
        event_map = settings.get("event_index", f"{platform}_event")
        self.data_store = SportsDataStore(
            dsn=settings.es.dsn,
            api_key=settings.es.api_key,
            languages=str_to_list(settings.get("languages", "en").lower()),
            platform=f"{{lang}}_{platform}",
            index_map={
                # "meta": settings.get(
                #     "meta_index", f"{self.platform}_meta"
                # ),
                # "team": settings.get(
                #     "team_index", f"{self.platform}_team"
                # ),
                "event": cast(str, event_map),
            },
        )
        self.base_score = settings.get("score", 0.5)
        self.max_suggestions = settings.get("max_suggestions", 10)
        self.mix_sports = settings.get("mix_sports", True)

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
