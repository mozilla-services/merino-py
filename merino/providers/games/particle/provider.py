"""Particle integration."""

import aiodogstatsd
import asyncio
import logging
import sentry_sdk

from pydantic import Json
from typing import Any

from merino.providers.games.particle.backends.filemanager import ParticleFileManagerError
from merino.providers.games.particle.backends.protocol import Particle, ParticleBackend
from merino.providers.games.particle.backends.utils import (
    validate_manifest_against_schema,
    validate_manifest_schema_version,
    ParticleManifestValidationError,
    RemoteChannelEnum,
)

logger = logging.getLogger(__name__)


class Provider:
    """Particle provider for games."""

    backend: ParticleBackend
    manifest_schema: Json
    manifest_schema_version: int
    metrics_client: aiodogstatsd.Client
    cron_task: asyncio.Task

    def __init__(
        self,
        backend: ParticleBackend,
        manifest_schema: Json,
        manifest_schema_version: int,
        metrics_client: aiodogstatsd.Client,
        name: str,
        enabled: bool = False,
        **kwargs: Any,
    ) -> None:
        self.backend = backend
        self.manifest_schema = manifest_schema
        self.manifest_schema_version = manifest_schema_version
        self.metrics_client = metrics_client
        self.name = name
        self._enabled = enabled

    def initialize(self) -> None:
        """Initialize the provider."""
        pass

    async def run_update_process(self) -> bool:
        """Initiate the process to attempt to update Particle game files."""
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
                "Particle game data fetch returned None - will retry on next cron tick."
            )

            return False
        else:
            return await self.process_remote_particle_data(manifest_json)

    async def process_remote_particle_data(self, remote_manifest_json: Json) -> bool:
        """Orchestration function to validate and upload new Particle game data files to GCS.
        Returns True only if some files (puzzle runtime and/or daily puzzle) were updated.
        """
        # default return values
        puzzle_updated = False
        runtime_updated = False

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
        try:
            gcs_manifest_json = await self.backend.fetch_manifest_json_from_gcs()
        except ParticleFileManagerError as ex:
            # if an exception occurs retrieving from GCS, return early to
            # ensure the next cron tick again attempts an update
            sentry_sdk.capture_exception(ex)
            return False

        # conditionally attempt to update file sets - daily puzzle and runtime
        puzzle_updated = await self.backend.update_channel_files(
            manifest_remote=remote_manifest_json,
            manifest_gcs=gcs_manifest_json,
            channel=RemoteChannelEnum.PUZZLE,
        )

        if puzzle_updated:
            logger.info("Particle daily files updated")

        runtime_updated = await self.backend.update_channel_files(
            manifest_remote=remote_manifest_json,
            manifest_gcs=gcs_manifest_json,
            channel=RemoteChannelEnum.RUNTIME,
        )

        if runtime_updated:
            logger.info("Particle runtime files updated")

        # if either set of files (daily puzzle or runtime) were updated, we can
        # consider this update successful
        return puzzle_updated or runtime_updated

    async def get_game_url(self) -> Particle | None:
        """Proxy get_game_url from Particle backend"""
        return await self.backend.get_game_url()
