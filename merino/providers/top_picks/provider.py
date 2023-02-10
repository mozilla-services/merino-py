# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Top Pick Navigational Queries Provider"""
import logging

from merino.exceptions import BackendError
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

    def __init__(
        self,
        backend: TopPicksBackend,
        score: float,
        name: str,
        enabled_by_default: bool = False,
    ) -> None:
        self.backend = backend
        self.score = score
        self._name = name
        self._enabled_by_default = enabled_by_default

    async def initialize(self) -> None:
        """Initialize the provider."""
        try:
            # Fetch Top Picks suggestions from domain list.
            self.top_picks_data: TopPicksData = await self.backend.fetch()

        except BackendError as backend_error:
            logger.warning(
                "Failed to fetch data from Top Picks Backend.",
                extra={"error message": f"{backend_error}"},
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
            self.top_picks_data.firefox_char_limit
            <= len(srequest.query)
            <= (self.top_picks_data.query_char_limit - 1)
        ):
            if ids := self.top_picks_data.short_domain_index.get(srequest.query):
                result = self.top_picks_data.results[ids[0]]
                return [Suggestion(**result, score=self.score)]

        # Ignore requests below or above character min/max after checking short domains above
        if (
            len(srequest.query) < self.top_picks_data.firefox_char_limit
            or len(srequest.query) > self.top_picks_data.query_max
        ):
            return []
        if ids := self.top_picks_data.primary_index.get(srequest.query):
            result = self.top_picks_data.results[ids[0]]
            return [Suggestion(**result, score=self.score)]
        elif ids := self.top_picks_data.secondary_index.get(srequest.query):
            result = self.top_picks_data.results[ids[0]]
            return [Suggestion(**result, score=self.score)]

        return []
