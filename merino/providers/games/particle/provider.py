"""Particle integration."""

import logging
from typing import Any

import aiodogstatsd

from merino.providers.games.particle.backends.protocol import Particle, ParticleBackend

logger = logging.getLogger(__name__)


class Provider:
    """Particle provider for games."""

    backend: ParticleBackend
    metrics_client: aiodogstatsd.Client

    def __init__(
        self,
        backend: ParticleBackend,
        metrics_client: aiodogstatsd.Client,
        name: str,
        enabled_by_default: bool = False,
        **kwargs: Any,
    ) -> None:
        self.backend = backend
        self.metrics_client = metrics_client
        self.name = name
        self._enabled_by_default = enabled_by_default
        super().__init__(**kwargs)

    async def initialize(self) -> None:
        """Initialize the provider."""

    async def get_game_url(self) -> Particle | None:
        """Proxy get_game_url from Particle backend"""
        return await self.backend.get_game_url()
