"""Provider for the Manifest data, fetched from GCS and stored in memory."""

import asyncio
import time
import logging

from merino.providers.manifest.backends.filemanager import GetManifestResultCode
from merino.utils import cron

from merino.providers.manifest.backends.protocol import (
    ManifestBackend,
    ManifestBackendError,
    ManifestData,
)

logger = logging.getLogger(__name__)


class Provider:
    """Provide access to in-memory manifest data fetched from GCS."""

    manifest_data: ManifestData | None
    cron_task: asyncio.Task
    resync_interval_sec: int
    cron_interval_sec: int
    last_fetch_at: float
    name: str

    def __init__(
        self,
        backend: ManifestBackend,
        resync_interval_sec: int,
        cron_interval_sec: int,
        name: str = "manifest",
    ) -> None:
        self.backend = backend
        self.name = name
        self.resync_interval_sec = resync_interval_sec
        self.cron_interval_sec = cron_interval_sec
        self.last_fetch_at = 0.0
        self.manifest_data = ManifestData(domains=[])
        self.data_fetched_event = asyncio.Event()

        super().__init__()

    async def initialize(self) -> None:
        """Initialize Manifest provider."""
        await self._fetch_data()

        cron_job = cron.Job(
            name="resync_manifest",
            interval=self.cron_interval_sec,
            condition=self._should_fetch,
            task=self._fetch_data,
        )
        self.cron_task = asyncio.create_task(cron_job())

    async def _fetch_data(self) -> None:
        """Cron fetch method to re-run after set interval.
        Does not set manifest_data if non-success code passed with None.
        """
        try:
            result_code, data = await self.backend.fetch()

            match GetManifestResultCode(result_code):
                case GetManifestResultCode.SUCCESS:
                    self.manifest_data = data
                    self.last_fetch_at = time.time()

                case GetManifestResultCode.SKIP:
                    return None

                case GetManifestResultCode.FAIL:
                    logger.error("Failed to fetch data from Manifest backend.")
                    return None
        except ManifestBackendError as err:
            logger.error("Failed to fetch data from Manifest backend: %s", err)

        finally:
            self.data_fetched_event.set()

    def _should_fetch(self) -> bool:
        """Determine if we should fetch new data based on time elapsed."""
        return (time.time() - self.last_fetch_at) >= self.resync_interval_sec

    def get_manifest_data(self) -> ManifestData | None:
        """Return manifest data"""
        return self.manifest_data

    async def get_manifest_data_via_async_client(self) -> ManifestData | None:
        """Return manifest data"""
        manifest_via_async = None

        try:
            manifest_via_async = await self.backend.fetch_via_async_gcs_client()
        except Exception:
            # We don't want our provider to blow up in case a RuntimeError is thrown by async_gcs_client module
            return None
        return manifest_via_async
