"""A backend wrapper for the Manifest Provider I/O Interactions (Remote-Only)."""

import logging

from merino.configs import settings
from merino.providers.manifest.backends.filemanager import (
    GetManifestResultCode,
    ManifestRemoteFilemanager,
)
from merino.providers.manifest.backends.protocol import ManifestData

logger = logging.getLogger(__name__)

GCS_BLOB_NAME = "top_picks_latest.json"


class ManifestBackend:
    """A remote-only backend that fetches the manifest file from GCS asynchronously, unmodified."""

    def __init__(self) -> None:
        """Initialize the Manifest backend."""
        pass

    async def fetch(self) -> tuple[GetManifestResultCode, ManifestData | None]:
        """Fetch the manifest data from GCS asynchronously.
        Returns:
            (SUCCESS, ManifestData): If new data is fetched from GCS.
            (FAIL, None): If there's an error with fetching or parsing.
        """
        return await self.fetch_manifest_data()

    async def fetch_manifest_data(
        self,
    ) -> tuple[GetManifestResultCode, ManifestData | None]:
        """Fetch manifest data from GCS through the remote filemanager."""
        remote_filemanager = ManifestRemoteFilemanager(
            gcs_bucket_path=settings.image_gcs.gcs_bucket,
            blob_name=GCS_BLOB_NAME,
        )

        return await remote_filemanager.get_file()
