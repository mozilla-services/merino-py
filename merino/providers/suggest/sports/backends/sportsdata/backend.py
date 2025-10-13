"""Handle incoming Sports related queries"""

from abc import abstractmethod
from dynaconf.base import LazySettings
from pydantic import HttpUrl
from typing import Protocol, cast

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
    base_score: float

    def __init__(self, settings: LazySettings, *args, **kwargs):
        super().__init__(*args, **kwargs)
        platform = settings.providers.sports.get("platform", "sports")
        event_map = settings.providers.sports.get("event_index", f"{platform}_event")
        self.data_store = SportsDataStore(
            dsn=settings.providers.sports.es.dsn,
            api_key=settings.providers.sports.es.api_key,
            languages=[
                lang.strip().lower()
                for lang in settings.providers.sports.get("languages", "en").split(",")
            ],
            platform=f"{{lang}}_{platform}",
            index_map={
                # "meta": settings.providers.sports.get(
                #     "meta_index", f"{self.platform}_meta"
                # ),
                # "team": settings.providers.sports.get(
                #     "team_index", f"{self.platform}_team"
                # ),
                "event": cast(str, event_map),
            },
            settings=settings,
        )
        self.base_score = settings.providers.sports.get("score", 0.5)
        self.max_suggestions = settings.providers.sports.get("max_suggestions", 10)

    async def query(
        self,
        query_string: str | None = None,
        language_code: str = "en",
        score: float = 0.5,
        url: HttpUrl | None = None,
    ) -> list[dict]:
        """Query the data store for terms and return a list of potential sporting events relevant to those terms.

        This relies on Elastic's internal tokenizer and full text search to scan the list of "terms" for matching results.
        Note that we would want to use elastic's term score as a multiplier for the returned suggestion score, since it would
        indicate how likely that suggestion matched the provided query.
        """
        # break the description into words
        if query_string:
            events = await self.data_store.search_events(q=query_string, language_code="en")
            suggestions: list[dict] = []
            for sport, events in events.items():
                if len(suggestions) > self.max_suggestions:
                    break
                suggestions.append(
                    dict(
                        sport=sport,
                        summary=SportSummary.from_events(
                            events=events,
                        ),
                    )
                )
            return suggestions
        return []

    async def shutdown(self) -> None:
        """Politely shut down the datastore"""
        await self.data_store.shutdown()
