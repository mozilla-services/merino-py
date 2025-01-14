"""A backend wrapper for the Manifest Provider I/O Interactions (Remote-Only)."""

import asyncio
import logging
from typing import Any

from merino.configs import settings
from merino.providers.manifest.backends.filemanager import (
    GetManifestResultCode,
    ManifestRemoteFilemanager,
)

logger = logging.getLogger(__name__)


class ManifestBackend:
    """A remote-only backend that fetches the manifest file from GCS, unmodified.

    It doesn't do any indexing or transformation — just returns the raw data.
    """

    def __init__(self) -> None:
        """Initialize the Manifest backend.

        GCS configuration is read from `settings.providers.manifest.*`:
        - `gcs_project`
        - `gcs_bucket`
        - `gcs_blob_name`
        """
        # You could store more custom config here if needed,
        # e.g., caching intervals or fallback flags.
        pass

    async def fetch(self) -> tuple[GetManifestResultCode, dict[str, Any] | None]:
        """Fetch the manifest data from GCS, offloading the synchronous I/O
        to a background thread.

        Returns:
            (SUCCESS, dict): If new data is fetched from GCS.
            (SKIP, None): If there's no new generation (blob unchanged).
            (FAIL, None): If there's an error with fetching or parsing.
        """
        return await asyncio.to_thread(self._maybe_get_data)

    def _maybe_get_data(self) -> tuple[GetManifestResultCode, dict[str, Any] | None]:
        """Actually do the GCS fetch from the remote filemanager. Returns the raw JSON
        unmodified, or (SKIP/FAIL) if there's no update or an error.
        """
        # Instantiate the remote filemanager with settings from your config
        remote_filemanager = ManifestRemoteFilemanager(
            gcs_project_path=settings.providers.manifest.gcs_project,
            gcs_bucket_path=settings.providers.manifest.gcs_bucket,
            blob_name=settings.providers.manifest.gcs_blob_name,
        )
        client = remote_filemanager.create_gcs_client()

        # get_file(...) returns (GetManifestResultCode, dict|None)
        result_code, manifest_data = remote_filemanager.get_file(client)

        if result_code == GetManifestResultCode.SUCCESS:
            logger.info("Manifest data loaded remotely from GCS.")
        elif result_code == GetManifestResultCode.SKIP:
            logger.debug("Manifest data was not updated (SKIP).")
        else:
            logger.error("Failed to fetch manifest from GCS (FAIL).")

        return result_code, manifest_data
