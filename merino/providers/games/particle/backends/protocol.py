"""Protocol for Particle provider backend."""

import aiodogstatsd

from httpx import AsyncClient
from pydantic import BaseModel, Field, Json
from typing import Protocol

from merino.providers.games.particle.backends.filemanager import ParticleRemoteFileManager
from merino.providers.games.particle.backends.utils import GameFile, RemoteChannelEnum
from merino.utils.gcs.gcs_uploader import GcsUploader


class Particle(BaseModel):
    """Model for Particle game data"""

    url: str = Field(description="Public URL for the game")


class ParticleBackend(Protocol):
    """Protocol for a weather backend that this provider depends on.

    Note: This only defines the methods used by the provider. The actual backend
    might define additional methods and attributes which this provider doesn't
    directly depend on.
    """

    gcs_uploader: GcsUploader
    http_client: AsyncClient
    metrics_client: aiodogstatsd.Client
    # remote endpoint
    particle_url_root: str
    # path to the manifest on the remote endpoint
    particle_url_path_manifest: str
    # manages files stored in GCS
    remote_file_manager: ParticleRemoteFileManager

    async def get_game_url(self) -> Particle | None:
        """Fetch the Particle game data.

        Returns:
            A Particle instance if data is available/valid, otherwise None.
        """
        ...

    async def fetch_manifest_json_from_remote(self) -> Json | None:
        """Retrieve the latest manifest JSON from Particle."""
        ...

    async def fetch_manifest_json_from_gcs(self) -> Json:
        """Retrieve the manifest json last stored in GCS."""
        ...

    async def update_channel_files(
        self, manifest_remote: Json, manifest_gcs: Json, channel: RemoteChannelEnum
    ) -> bool:
        """Attempt to update files in GCS for the given channel."""
        ...

    async def stage_channel_files(self, files: list[GameFile]) -> tuple[bool, list[GameFile]]:
        """Orchestration function to download remote files for the given channel to a temporary directory,
        verify their SHAs, and, if valid, upload them to GCS. If one file fails, we cancel the rest of the checks, as all files in a set must
        validate and upload successfully.

        This will prepare the channel to be "deployed".

        Returns overall success status and the list of GameFiles with their verified/uploaded statuses updated.
        """
        ...

    async def deploy_channel_files(
        self, files: list[GameFile], manifest_remote: Json, manifest_gcs: Json
    ) -> bool:
        """Deploy files from the 'green' folder in GCS to the root."""
        ...
