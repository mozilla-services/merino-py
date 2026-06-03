"""Particle integration."""

import aiodogstatsd
import asyncio
import logging
import sentry_sdk
import time

from pydantic import Json
from typing import Any

from merino.providers.games.particle.backends.filemanager import ParticleFileManagerError
from merino.providers.games.particle.backends.protocol import Particle, ParticleBackend
from merino.providers.games.particle.backends.utils import (
    update_channel_files,
    validate_manifest_against_schema,
    validate_manifest_schema_version,
    ParticleManifestValidationError,
    RemoteChannelEnum,
)
from merino.utils import cron

logger = logging.getLogger(__name__)


class Provider:
    """Particle provider for games."""

    backend: ParticleBackend
    cron_interval_sec: float
    last_successful_update_at: float
    manifest_schema: Json
    manifest_schema_version: int
    metrics_client: aiodogstatsd.Client
    cron_task: asyncio.Task
    resync_interval_sec: float

    def __init__(
        self,
        backend: ParticleBackend,
        cron_interval_sec: float,
        manifest_schema: Json,
        manifest_schema_version: int,
        metrics_client: aiodogstatsd.Client,
        name: str,
        resync_interval_sec: float,
        enabled: bool = False,
        **kwargs: Any,
    ) -> None:
        self.backend = backend
        self.cron_interval_sec = cron_interval_sec
        self.last_successful_update_at = 0.0
        self.manifest_schema = manifest_schema
        self.manifest_schema_version = manifest_schema_version
        self.metrics_client = metrics_client
        self.name = name
        self.resync_interval_sec = resync_interval_sec
        self._enabled = enabled
        super().__init__(**kwargs)

    async def initialize(self) -> None:
        """Initialize the provider."""
        if self._enabled:
            # create a cron job to update particle game files
            cron_job = cron.Job(
                name="update_particle_game_data",
                interval=self.cron_interval_sec,
                condition=self._should_fetch_data,
                task=self._fetch_game_data,
            )

            self.cron_task = asyncio.create_task(cron_job())

    def _should_fetch_data(self) -> bool:
        """Check if we should fetch Particle game data from the internet."""
        return (time.time() - self.last_successful_update_at) >= self.resync_interval_sec

    async def _fetch_game_data(self) -> None:
        manifest_json: Json | None = None

        try:
            # if successful, returns Json
            manifest_json = await self.backend.fetch_manifest_json_from_remote()
        except Exception as ex:
            logger.warning(
                "Failed to fetch Particle game data from remote endpoint", extra={"error": str(ex)}
            )

            sentry_sdk.capture_exception(ex)

        if manifest_json is None:
            logger.warning(
                f"Particle game data fetch returned None - will retry on next cron tick ({self.cron_interval_sec} seconds)"
            )
        else:
            particle_updated = await self.process_remote_particle_data(manifest_json)

            # only update the last success time if we actually updated some files
            if particle_updated:
                self.last_successful_update_at = time.time()

    async def process_remote_particle_data(self, remote_manifest_json: Json) -> bool:
        """Orchestration function to validate and upload new Particle game data files to GCS.
        Returns True only if some files (puzzle runtime and/or daily puzzle) were updated.
        """
        # ensure the remote schema is valid
        # this will raise if the schema is invalid
        try:
            validate_manifest_against_schema(remote_manifest_json, self.manifest_schema)
        except ParticleManifestValidationError as ex:
            sentry_sdk.capture_exception(ex)
            return False

        # ensure the schema version is as expected
        # this will raise if the schema version doesn't match
        try:
            validate_manifest_schema_version(remote_manifest_json, self.manifest_schema_version)
        except ParticleManifestValidationError as ex:
            sentry_sdk.capture_exception(ex)
            return False

        # get the manifest file we last stored in GCS to determine if the
        # remote version is newer.
        # returns None if no file is found in GCS, will raise if there's an
        # error retrieving from GCS.
        try:
            gcs_manifest_json = await self.backend.fetch_manifest_json_from_gcs()
        except ParticleFileManagerError:
            # if an exception occurs retrieving from GCS, return early to
            # ensure the next cron tick again attempts an update
            return False

        # conditionally attempt to update file sets - daily puzzle and runtime
        puzzle_updated = await update_channel_files(
            manifest_remote=remote_manifest_json,
            manifest_gcs=gcs_manifest_json,
            channel=RemoteChannelEnum.PUZZLE,
        )

        runtime_updated = await update_channel_files(
            manifest_remote=remote_manifest_json,
            manifest_gcs=gcs_manifest_json,
            channel=RemoteChannelEnum.RUNTIME,
        )

        # if either set of files (daily puzzle or runtime) were updated, we can
        # consider this update successful
        return puzzle_updated or runtime_updated

    async def get_game_url(self) -> Particle | None:
        """Proxy get_game_url from Particle backend"""
        return await self.backend.get_game_url()
