"""File manager class for the Particle backend."""

import json
import logging
import sentry_sdk

from json import JSONDecodeError
from typing import Any

from merino.exceptions import FilemanagerError
from merino.utils.gcs.gcs_uploader import GcsUploader

logger = logging.getLogger(__name__)


class ParticleFileManagerError(FilemanagerError):
    """Error loading local Particle manifest schema validator file."""


class ParticleLocalFileManager:
    """File manager for processing local Particle data."""

    # path to the local manifest schema file
    static_manifest_schema_file_path: str

    def __init__(self, static_manifest_schema_file_path: str) -> None:
        self.static_manifest_schema_file_path = static_manifest_schema_file_path

    def get_manifest_schema(self) -> dict[str, Any]:
        """Read local manifest schema validator file."""
        try:
            """Retrieve manifest schema JSON when this module loads."""
            with open(self.static_manifest_schema_file_path, "r") as f:
                manifest_schema: dict = json.load(f)
                return manifest_schema
        except OSError as os_ex:
            error_msg = f"Cannot open file '{self.static_manifest_schema_file_path}"

            sentry_sdk.capture_exception(os_ex)

            raise ParticleFileManagerError(error_msg) from os_ex
        except JSONDecodeError as json_ex:
            error_msg = f"Cannot decode JSON file '{self.static_manifest_schema_file_path}"

            sentry_sdk.capture_exception(json_ex)

            raise ParticleFileManagerError(error_msg) from json_ex


class ParticleRemoteFileManager:
    """Filemanager for processing remote (GCS) Particle data."""

    gcs_client: GcsUploader
    manifest_file_name: str

    def __init__(
        self,
        gcs_client: GcsUploader,
        manifest_file_name: str,
    ) -> None:
        """Initialize the remote filemanager."""
        self.gcs_client = gcs_client
        self.manifest_file_name = manifest_file_name

    def get_manifest_file(self) -> dict[str, Any] | None:
        """Read remote manifest file.

        Raises:
            ParticleFileManagerError: If the manifest file cannot be accessed.
        Returns:
            Dictionary containing manifest.
        """
        try:
            blob = self.gcs_client.get_file_by_name(self.manifest_file_name)

            if blob is not None:
                blob_data = blob.download_as_text()
                file_contents: dict = json.loads(blob_data)
                logger.info("Successfully loaded remote Particle manifest file.")

                return file_contents

            return None
        except Exception as ex:
            error_msg = f"Error retrieving remote Particle manifest file. {ex}"

            logger.error(error_msg)

            sentry_sdk.capture_exception(ex)

            raise ParticleFileManagerError(error_msg) from ex
