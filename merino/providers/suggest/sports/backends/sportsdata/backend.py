"""Handle incoming Sports related queries"""

import json
import re
from dynaconf.base import Settings
from typing import Protocol, Any, AnyStr

from merino.providers.manifest.backends.protocol import ManifestData
from merino.providers.suggest.sports.backends import SportSuggestion
from merino.providers.suggest.sports.backends.sportsdata.common.data import (
    ElasticDataStore,
    Team,
    Event,
)


class SportsDataBackend(Protocol):
    """Provide the methods specific to this provider for fulfilling the request"""

    manifest_data: ManifestData
    data_store: ElasticDataStore
    word_breaker: re.Pattern

    def __init__(self, manifest_data: ManifestData, settings: Settings):
        self.manifest_data = manifest_data
        self.data_store = ElasticDataStore(
            dsn=settings["dsn"], api_key=settings["api_key"]
        )
        self.word_breaker = re.compile(r"(\w+)")

    def get_events(teams: list[Team]) -> list[Event]:
        """Search each `Sport`'s local event cache for anything that contains the team ids."""
        import pdb

        pdb.set_trace()
        return

    async def query(
        self, query_string: str | None = None, language_code: str = "en"
    ) -> list[SportSuggestion]:
        """Eventually use clever logic in order to return an emoji specific to the
        passed description string, but for now, just return the default in a list.
        """
        # break the description into words
        words = self.word_breaker.findall(query_string)
        teams = []
        for word in words:
            team = await self.data_store.search(word, language_code="en")
            if team:
                teams.append(team)
        if len(teams) > 1:
            events = self.get_events(teams)
            return [event.as_suggestion() for event in events]
        return []
