"""A backend wrapper for the Manifest Provider I/O Interactions (Remote-Only)."""

import asyncio
import logging

from merino.configs import settings
from merino.providers.manifest.backends.filemanager import (
    GetManifestResultCode,
    ManifestRemoteFilemanager,
)
from merino.providers.manifest.backends.protocol import ManifestData
from merino.utils.gcs.async_gcs_client import AsyncGcsClient

logger = logging.getLogger(__name__)

GCS_BLOB_NAME = "top_picks_latest.json"


class ManifestBackend:
    """A remote-only backend that fetches the manifest file from GCS, unmodified."""

    def __init__(self) -> None:
        """Initialize the Manifest backend."""
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
            gcs_project_path=settings.image_manifest.gcs_project,
            gcs_bucket_path=settings.image_manifest.gcs_bucket,
            blob_name=GCS_BLOB_NAME,
        )

        result_code, manifest_data = remote_filemanager.get_file()

        match GetManifestResultCode(result_code):
            case GetManifestResultCode.SUCCESS:
                logger.info("Manifest data loaded remotely from GCS.")
                return result_code, manifest_data

            case GetManifestResultCode.SKIP:
                logger.info("Manifest data was not updated (SKIP).")
                return result_code, None

            case GetManifestResultCode.FAIL:
                logger.error("Failed to fetch manifest from GCS (FAIL).")
                return result_code, None

    async def fetch_via_async_gcs_client(self) -> ManifestData | None:
        """Create an async gcs client and download the same manifest blob
        this is temporary redundant logic just to test out the async client downloads from gcs
        to mainly test if auth is working properly with this client
        """
        async_gcs_client = AsyncGcsClient()
        manifest_via_async = await async_gcs_client.get_manifest_from_blob(
            bucket_name=settings.image_manifest.gcs_bucket, blob_name=GCS_BLOB_NAME
        )

        return manifest_via_async
