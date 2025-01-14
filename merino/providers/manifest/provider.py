"""Provider for the Manifest data, fetched from GCS and stored in memory."""

import asyncio
import time
import logging

from merino.providers.manifest.backends.filemanager import GetManifestResultCode
from merino.utils import cron
from merino.providers.base import BaseProvider, SuggestionRequest, BaseSuggestion
from merino.exceptions import BackendError
from merino.configs import settings
from merino.providers.manifest.backends.protocol import ManifestBackend

logger = logging.getLogger(__name__)


class Provider(BaseProvider):
    """Provide access to in-memory manifest data fetched from GCS."""

    def __init__(
        self,
        backend: ManifestBackend,
        name: str = "manifest",
        resync_interval_sec=settings.providers.manifest.resync_interval_sec,
        cron_interval_sec=settings.providers.manifest.cron_interval_sec,
    ) -> None:
        super().__init__()
        self.backend = backend
        self._name = name
        self.resync_interval_sec = resync_interval_sec
        self.cron_interval_sec = cron_interval_sec
        self.last_fetch_at = 0.0

        self.manifest_data: dict | None = None
        self.cron_task: asyncio.Task | None = None

    async def initialize(self) -> None:
        """Initialize Manifest provider."""
        try:
            result_code, data = await self.backend.fetch()
            if result_code == GetManifestResultCode.SUCCESS and data is not None:
                self.manifest_data = data
                self.last_fetch_at = time.time()
        except BackendError as err:
            logger.error("Failed to fetch manifest on startup: %s", err)

        cron_job = cron.Job(
            name="resync_manifest",
            interval=self.cron_interval_sec,
            condition=self._should_fetch,
            task=self._fetch_manifest_data,
        )
        self.cron_task = asyncio.create_task(cron_job())

    async def _fetch_manifest_data(self) -> None:
        try:
            result_code, data = await self.backend.fetch()
            if result_code == GetManifestResultCode.SUCCESS and data is not None:
                self.manifest_data = data
                self.last_fetch_at = time.time()
        except BackendError as err:
            logger.error("Failed to fetch manifest on startup: %s", err)

    def _should_fetch(self) -> bool:
        """Determine if we should fetch new data based on time elapsed."""
        return bool((time.time() - self.last_fetch_at) >= self.resync_interval_sec)

    async def query(self, params: SuggestionRequest) -> list[BaseSuggestion]:
        """Query Manifest data and return it as is.
        This provider simply returns the raw manifest data from GCS.

        Args:
            params: The suggestion request parameters

        Returns:
            An empty list for now since we haven't implemented suggestion conversion
        """
        if self.manifest_data is None:
            return []

        # For now, return empty list since we need to implement conversion
        # from manifest_data to BaseSuggestion objects
        return []
