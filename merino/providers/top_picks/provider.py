# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Top Pick Navigational Queries Provider"""
import asyncio
import logging
import time
from typing import Any

from merino import cron
from merino.config import settings
from merino.exceptions import BackendError
from merino.providers.base import BaseProvider, BaseSuggestion, SuggestionRequest
from merino.providers.top_picks.backends.filemanager import GetFileResultCode
from merino.providers.top_picks.backends.protocol import TopPicksBackend, TopPicksData
from merino.providers.top_picks.backends.top_picks import DomainDataSource

logger = logging.getLogger(__name__)


class Suggestion(BaseSuggestion):
    """Model for Top Pick Suggestion."""

    block_id: int
    is_top_pick: bool


class Provider(BaseProvider):
    """Top Pick Suggestion Provider."""

    top_picks_data: TopPicksData
    cron_task: asyncio.Task
    resync_interval_sec: int
    cron_interval_sec: int
    last_fetch_at: float

    def __init__(
        self,
        backend: TopPicksBackend,
        score: float,
        name: str,
        enabled_by_default: bool = False,
        resync_interval_sec=settings.providers.top_picks.resync_interval_sec,
        cron_interval_sec=settings.providers.top_picks.cron_interval_sec,
        **kwargs: Any,
    ) -> None:
        self.backend = backend
        self.score = score
        self._name = name
        self._enabled_by_default = enabled_by_default
        self.resync_interval_sec = resync_interval_sec
        self.cron_interval_sec = cron_interval_sec
        self.last_fetch_at = 0
        super().__init__(**kwargs)

    async def initialize(self) -> None:
        """Initialize the provider."""
        try:
            # Fetch Top Picks suggestions from domain list.
            result_code, result = await self.backend.fetch()

            match GetFileResultCode(result_code):
                case GetFileResultCode.SUCCESS:
                    self.top_picks_data: TopPicksData = result  # type: ignore
                    self.last_fetch_at = time.time()
                case GetFileResultCode.SKIP:
                    return None
                case GetFileResultCode.FAIL:
                    logger.error("Failed to fetch data from Top Picks Backend.")
                    return None
        except BackendError as backend_error:
            logger.error(
                "Failed to fetch data from Top Picks Backend.",
                extra={"error message": f"{backend_error}"},
            )

        # Run a cron job that will periodically check whether to update domain file.
        # Only runs when domain source set to `remote`.
        if (
            settings.providers.top_picks.domain_data_source
            == DomainDataSource.REMOTE.value
        ):
            cron_job = cron.Job(
                name="resync_domain_file",
                interval=self.cron_interval_sec,
                condition=self._should_fetch,
                task=self._fetch_top_picks_data,
            )
            # Store the created task on the instance variable. Otherwise it will get
            # garbage collected because asyncio's runtime only holds a weak
            # reference to it.
            self.cron_task = asyncio.create_task(cron_job())

    async def _fetch_top_picks_data(self) -> None:
        """Cron fetch method to re-run after set interval.
        Does not set top_picks_data if non-success code passed with None.
        """
        try:
            # Fetch Top Picks suggestions from domain list.
            result_code, result = await self.backend.fetch()
            match GetFileResultCode(result_code):
                case GetFileResultCode.SUCCESS:
                    self.top_picks_data: TopPicksData = result  # type: ignore
                    self.last_fetch_at = time.time()
                case GetFileResultCode.SKIP:
                    return None
                case GetFileResultCode.FAIL:
                    logger.error("Failed to fetch data from Top Picks Backend.")
                    return None
        except BackendError as backend_error:
            logger.error(
                "Failed to fetch data from Top Picks Backend.",
                extra={"error message": f"{backend_error}"},
            )

    def hidden(self) -> bool:  # noqa: D102
        return False

    def _should_fetch(self) -> bool:
        """Determine if a more recent file should be requested."""
        return (time.time() - self.last_fetch_at) >= self.resync_interval_sec

    def normalize_query(self, query: str) -> str:
        """Convert a query string to lowercase and remove trailing spaces."""
        return query.strip().lower()

    async def query(self, srequest: SuggestionRequest) -> list[BaseSuggestion]:
        """Query Top Pick data and return suggestions."""
        # Ignore https:// and http://
        if srequest.query.startswith("http"):
            return []

        qlen: int = len(srequest.query)
        query: str = srequest.query
        ids: list[int] | None = None

        match qlen:
            case qlen if (
                self.top_picks_data.firefox_char_limit
                <= qlen
                < self.top_picks_data.query_char_limit
            ):
                ids = self.top_picks_data.short_domain_index.get(query)
            case qlen if (
                self.top_picks_data.query_char_limit
                <= qlen
                <= self.top_picks_data.query_max
            ):
                ids = self.top_picks_data.primary_index.get(
                    query
                ) or self.top_picks_data.secondary_index.get(query)
            case _:
                ids = None
        return (
            [Suggestion(**self.top_picks_data.results[ids[0]], score=self.score)]
            if ids
            else []
        )
