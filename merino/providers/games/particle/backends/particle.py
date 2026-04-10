"""Particle game backend."""

import logging
import aiodogstatsd

from merino.configs import settings
from merino.providers.games.particle.backends.protocol import Particle
from merino.utils.gcs.gcs_uploader import GcsUploader

logger = logging.getLogger(__name__)

# Module-level variable as retrieving from settings each time is expensive.
_game_url = settings.games_providers.particle.game_url


class ParticleBackend:
    """Backend for managing and returning Particle game data."""

    gcs_uploader: GcsUploader
    metrics_client: aiodogstatsd.Client

    def __init__(
        self,
        gcs_uploader: GcsUploader,
        metrics_client: aiodogstatsd.Client,
    ) -> None:
        """Initialize the Polygon backend."""
        self.gcs_uploader = gcs_uploader
        self.metrics_client = metrics_client

    async def get_game_url(self) -> Particle | None:
        """Return the public URL for the Particle game"""
        return Particle(url=_game_url)
