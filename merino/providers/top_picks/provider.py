# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Top Pick Navigational Queries Provider"""
import logging
from collections import defaultdict

from merino.providers.base import BaseProvider, BaseSuggestion, SuggestionRequest
from merino.providers.top_picks.backends.protocol import TopPicksBackend, TopPicksData

logger = logging.getLogger(__name__)


class Suggestion(BaseSuggestion):
    """Model for Top Pick Suggestion."""

    block_id: int
    is_top_pick: bool


class Provider(BaseProvider):
    """Top Pick Suggestion Provider."""

    top_picks_data: TopPicksData
    primary_index: defaultdict = defaultdict(list)
    secondary_index: defaultdict = defaultdict(list)
    short_domain_index: defaultdict = defaultdict(list)
    results: list[Suggestion]
    query_min: int
    query_max: int

    def __init__(
        self,
        backend: TopPicksBackend,
        name: str,
        enabled_by_default: bool = False,
    ) -> None:
        self.backend = backend
        self._name = name
        self._enabled_by_default = enabled_by_default

    async def initialize(self) -> None:
        """Initialize the provider."""
        try:
            # Fetch Top Picks suggestions from domain list.
            self.top_picks_data: TopPicksData = await self.backend.fetch()
            self.primary_index = self.top_picks_data.primary_index
            self.secondary_index = self.top_picks_data.secondary_index
            self.short_domain_index = self.top_picks_data.short_domain_index
            self.results: list[Suggestion] = [
                Suggestion(**result) for result in self.top_picks_data.results
            ]
            self.query_min = self.top_picks_data.index_char_range[0]
            self.query_max = self.top_picks_data.index_char_range[1]
            self.query_char_limit = self.top_picks_data.query_char_limit
            self.firefox_char_limit = self.top_picks_data.firefox_char_limit

        except Exception as e:
            logger.warning(
                "Failed to fetch data from Top Picks Backend.",
                extra={"error message": f"{e}"},
            )

    def hidden(self) -> bool:  # noqa: D102
        return False

    async def query(self, srequest: SuggestionRequest) -> list[BaseSuggestion]:
        """Query Top Pick data and return suggestions."""
        # Ignore https:// and http://
        if srequest.query.startswith("http"):
            return []
        # Suggestions between Firefox char min of 2 and query limit - 1 for short domains
        if (
            self.firefox_char_limit
            <= len(srequest.query)
            <= (self.query_char_limit - 1)
        ):
            if ids := self.short_domain_index.get(srequest.query):
                res = self.results[ids[0]]
                return [res]

        # Ignore requests below or above character min/max after checking short domains above
        if (
            len(srequest.query) < self.firefox_char_limit
            or len(srequest.query) > self.query_max
        ):
            return []
        if ids := self.primary_index.get(srequest.query):
            res = self.results[ids[0]]
            return [res]
        elif ids := self.secondary_index.get(srequest.query):
            res = self.results[ids[0]]
            return [res]

        return []
