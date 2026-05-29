"""Particle game backend."""

import aiodogstatsd
import asyncio
import logging
import orjson
import sentry_sdk

from httpx import AsyncClient, HTTPError, Response
from pydantic import Json

from merino.configs import settings
from merino.providers.games.particle.backends.protocol import Particle
from merino.providers.games.particle.backends.filemanager import ParticleRemoteFileManager
from merino.utils.gcs.gcs_uploader import GcsUploader

logger = logging.getLogger(__name__)

# Module-level variable as retrieving from settings each time is expensive.
_game_url = settings.games_providers.particle.game_url


class ParticleBackend:
    """Backend for managing and returning Particle game data."""

    gcs_uploader: GcsUploader
    http_client: AsyncClient
    metrics_client: aiodogstatsd.Client
    # remote endpoint
    particle_url_root: str
    # path to the manifest on the remote endpoint
    particle_url_path_manifest: str
    # manages files stored in GCS
    remote_file_manager: ParticleRemoteFileManager

    def __init__(
        self,
        gcs_uploader: GcsUploader,
        http_client: AsyncClient,
        manifest_gcs_file_name: str,
        metrics_client: aiodogstatsd.Client,
        particle_url_root: str,
        particle_url_path_manifest: str,
        remote_file_manager: ParticleRemoteFileManager,
    ) -> None:
        """Initialize the Polygon backend."""
        self.gcs_uploader = gcs_uploader
        self.http_client = http_client
        self.metrics_client = metrics_client
        self.particle_url_root = particle_url_root
        self.particle_url_path_manifest = particle_url_path_manifest
        self.remote_file_manager = remote_file_manager

    async def get_game_url(self) -> Particle | None:
        """Return the public URL for the Particle game"""
        return Particle(url=_game_url)

    async def fetch_manifest_json_from_remote(self) -> Json | None:
        """Retrieve the latest manifest JSON from Particle"""
        manifest: Response | None = None
        manifest_json: Json | None = None

        # try to get the manifest from the internet
        try:
            manifest = await self.http_client.get(
                f"{self.particle_url_root}{self.particle_url_path_manifest}"
            )

            manifest.raise_for_status()
        except HTTPError as ex:
            error_msg = f"HTTP error when fetching Particle manifest: {ex}"

            logger.error(error_msg)

            sentry_sdk.capture_exception(ex)

        # if the manifest was retrieved and has a content property, we're good
        if manifest and manifest.content:
            # try to convert the contents of manifest.content to JSON
            try:
                manifest_json = orjson.loads(manifest.content)
            except ValueError as ex:
                error_msg = "JSON error when converting Particle response"

                logger.error(error_msg)

                sentry_sdk.capture_exception(ex)

        # returning json or None
        return manifest_json

    async def fetch_manifest_json_from_gcs(self) -> Json | None:
        """Retrieve the manifest json last stored in GCS"""
        # the gcp client library is synchronous - wrap in an async thread so
        # we don't block processing
        return await asyncio.to_thread(self.remote_file_manager.get_manifest_file)
