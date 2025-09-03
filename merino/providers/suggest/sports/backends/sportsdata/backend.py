"""Handle incoming Sports related queries"""

import json
import re
from dynaconf.base import LazySettings
from typing import Protocol, Any, AnyStr

from merino.providers.manifest.backends.protocol import ManifestData
from merino.providers.suggest.sports.backends import SportSuggestion
from merino.providers.suggest.sports.backends.sportsdata.data import (
    DataStore,
)


class SportsDataBackend(Protocol):
    """Provide the methods specific to this provider for fulfilling the request"""

    manifest_data: ManifestData
    data_store: DataStore
    word_breaker: re.Pattern

    def __init__(self, manifest_data: ManifestData, settings: LazySettings):
        self.manifest_data = manifest_data
        self.data_store = DataStore(settings=settings)
        self.word_breaker = re.compile(r"(\w+)")

    async def query(self, query_string: str | None = None) -> list[SportSuggestion]:
        """Eventually use clever logic in order to return an emoji specific to the
        passed description string, but for now, just return the default in a list.
        """
        # break the description into words
        words = self.word_breaker.findall(query_string)
        teams = []
        for word in words:
            team = self.data_store.get_team(word)
            if team:
                teams.append(team)
        if len(teams) > 1:
            events = self.data_store.get_events(teams)
            return [event.as_suggestion() for event in events]
        return []
