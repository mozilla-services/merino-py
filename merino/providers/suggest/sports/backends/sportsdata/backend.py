"""Handle incoming Sports related queries"""

import json
import re
from dynaconf.base import LazySettings
from typing import Protocol, Any, AnyStr

from merino.providers.manifest.backends.protocol import ManifestData
from merino.providers.suggest.sports.backends import SportSuggestion
from merino.providers.suggest.sports.backends.sportsdata.common.data import (
    Team,
    Event,
)
from merino.providers.suggest.sports.backends.sportsdata.common.elastic import (
    ElasticDataStore,
)


class SportsDataBackend(Protocol):
    """Provide the methods specific to this provider for fulfilling the request"""

    manifest_data: ManifestData
    data_store: ElasticDataStore
    word_breaker: re.Pattern

    def __init__(self, manifest_data: ManifestData, settings: LazySettings):
        self.manifest_data = manifest_data
        self.data_store = ElasticDataStore(settings=settings)

    async def query(
        self, query_string: str | None = None, language_code: str = "en"
    ) -> list[SportSuggestion]:
        """Eventually use clever logic in order to return an emoji specific to the
        passed description string, but for now, just return the default in a list.
        """
        # break the description into words
        if query_string:
            events = await self.data_store.search_events(
                q=query_string, language_code="en"
            )
            # TODO: convert to suggestions
            return events
        return []
