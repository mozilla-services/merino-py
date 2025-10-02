"""Handle incoming Sports related queries"""

import re
from abc import abstractmethod
from dynaconf.base import LazySettings
from pydantic import HttpUrl
from typing import Protocol, cast

from merino.providers.suggest.base import BaseSuggestion
from merino.providers.suggest.sports.backends import SportSuggestion
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
    word_breaker: re.Pattern

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

    async def query(
        self,
        query_string: str | None = None,
        language_code: str = "en",
        score: float = 0.5,
        url: HttpUrl | None = None,
    ) -> list[BaseSuggestion]:
        """Eventually use clever logic in order to return an emoji specific to the
        passed description string, but for now, just return the default in a list.
        """
        # break the description into words
        if query_string:
            events = await self.data_store.search_events(q=query_string, language_code="en")
            # TODO: convert to suggestions
            suggestions = []
            for sport, events in events.items():
                suggestions.append(
                    cast(
                        BaseSuggestion,
                        SportSuggestion.from_events(
                            sport_name=sport,
                            query=query_string,
                            rating=0,
                            events=events,
                        ),
                    )
                )
            return suggestions
        return []

    async def shutdown(self) -> None:
        """Politely shut down the datastore"""
        await self.data_store.shutdown()
