"""A backend wrapper for the Manifest Provider I/O Interactions (Remote-Only)."""

import asyncio
import logging

from merino.configs import settings
from merino.providers.manifest.backends.filemanager import (
    GetManifestResultCode,
    ManifestRemoteFilemanager,
)
from merino.providers.manifest.backends.protocol import ManifestData

logger = logging.getLogger(__name__)


class ManifestBackend:
    """A remote-only backend that fetches the manifest file from GCS, unmodified.
    It doesn't do any indexing or transformation — just returns the raw data.
    """

    def __init__(self) -> None:
        """Initialize the Manifest backend.
        GCS configuration is read from `settings.manifest.*`:
        - `gcs_project`
        - `gcs_bucket`
        - `gcs_blob_name`
        """
        # You could store more custom config here if needed,
        # e.g., caching intervals or fallback flags.
        pass

    async def fetch(self) -> tuple[GetManifestResultCode, ManifestData | None]:
        """Fetch the manifest data from GCS, offloading the synchronous I/O
        to a background thread.
        Returns:
            (SUCCESS, ManifestData): If new data is fetched from GCS.
            (SKIP, None): If there's no new generation (blob unchanged).
            (FAIL, None): If there's an error with fetching or parsing.
        """
        return await asyncio.to_thread(self.fetch_manifest_data)

    def fetch_manifest_data(self) -> tuple[GetManifestResultCode, ManifestData | None]:
        """Fetch manifest data from GCS through the remote filemanager."""
        remote_filemanager = ManifestRemoteFilemanager(
            gcs_project_path=settings.manifest.gcs_project,
            gcs_bucket_path=settings.manifest.gcs_bucket,
            blob_name=settings.manifest.gcs_blob_name,
        )

        result_code, manifest_data = remote_filemanager.get_file()

        match GetManifestResultCode(result_code):
            case GetManifestResultCode.SUCCESS:
                logger.info("Manifest data loaded remotely from GCS.")
                return (result_code, manifest_data)

            case GetManifestResultCode.SKIP:
                logger.debug("Manifest data was not updated (SKIP).")
                return (result_code, None)

            case GetManifestResultCode.FAIL:
                logger.error("Failed to fetch manifest from GCS (FAIL).")
                return (result_code, None)
