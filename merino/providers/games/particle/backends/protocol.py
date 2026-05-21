"""Protocol for Particle provider backend."""

from pydantic import BaseModel, Field, Json

from typing import Protocol


class Particle(BaseModel):
    """Model for Particle game data"""

    url: str = Field(description="Public URL for the game")


class ParticleBackend(Protocol):
    """Protocol for a weather backend that this provider depends on.

    Note: This only defines the methods used by the provider. The actual backend
    might define additional methods and attributes which this provider doesn't
    directly depend on.
    """

    async def get_game_url(self) -> Particle | None:
        """Fetch the Particle game data.

        Returns:
            A Particle instance if data is available/valid, otherwise None.
        """
        ...

    async def fetch_manifest_json_from_remote(self) -> Json | None:
        """Retrieve the latest manifest JSON from Particle"""
        ...

    async def fetch_manifest_json_from_gcs(self) -> Json | None:
        """Retrieve the manifest json last stored in GCS"""
        ...
