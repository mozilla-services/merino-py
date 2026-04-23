"""A backend wrapper for the Manifest Provider I/O Interactions (Remote-Only)."""

import logging

from merino.configs import settings
from merino.providers.manifest.backends.filemanager import ManifestRemoteFilemanager
from merino.providers.manifest.backends.protocol import ManifestFetchResult

logger = logging.getLogger(__name__)

GCS_BLOB_NAME = "top_picks_latest.json"


class ManifestBackend:
    """A remote-only backend that fetches the manifest file from GCS asynchronously, unmodified."""

    def __init__(self) -> None:
        """Initialize the Manifest backend."""
        pass

    async def fetch(self) -> ManifestFetchResult:
        """Fetch the manifest data from GCS asynchronously."""
        return await self.fetch_manifest_data()

    async def fetch_manifest_data(self) -> ManifestFetchResult:
        """Fetch manifest data from GCS through the remote filemanager."""
        remote_filemanager = ManifestRemoteFilemanager(
            gcs_bucket_path=settings.image_gcs.gcs_bucket,
            blob_name=GCS_BLOB_NAME,
        )

        return await remote_filemanager.get_file()
