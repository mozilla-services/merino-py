"""Particle game backend."""

import aiodogstatsd
import logging
import orjson

from httpx import AsyncClient, HTTPError, Response
from pydantic import Json

from merino.configs import settings
from merino.providers.games.particle.backends.protocol import Particle
from merino.utils.gcs.gcs_uploader import GcsUploader

logger = logging.getLogger(__name__)

# Module-level variable as retrieving from settings each time is expensive.
_game_url = settings.games_providers.particle.game_url


class ParticleBackend:
    """Backend for managing and returning Particle game data."""

    gcs_uploader: GcsUploader
    http_client: AsyncClient
    metrics_client: aiodogstatsd.Client
    particle_url_root: str
    particle_url_path_manifest: str

    def __init__(
        self,
        gcs_uploader: GcsUploader,
        http_client: AsyncClient,
        metrics_client: aiodogstatsd.Client,
        particle_url_root: str,
        particle_url_path_manifest: str,
    ) -> None:
        """Initialize the Polygon backend."""
        self.gcs_uploader = gcs_uploader
        self.http_client = http_client
        self.metrics_client = metrics_client
        self.particle_url_root = particle_url_root
        self.particle_url_path_manifest = particle_url_path_manifest

    async def get_game_url(self) -> Particle | None:
        """Return the public URL for the Particle game"""
        return Particle(url=_game_url)

    async def _fetch_manifest_json(self) -> Json | None:
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
            logger.error(f"HTTP error when fetching Particle manifest: {ex}")

        # if the manifest was retrieved and has a content property, we're good
        if manifest and manifest.content:
            # try to convert the contents of manifest.content to JSON
            try:
                manifest_json = orjson.loads(manifest.content)
            except ValueError:
                logger.error("JSON error when converting Particle response")

        # returning json or None
        return manifest_json
