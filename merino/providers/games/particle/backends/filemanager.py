"""File manager class for the Particle backend."""

import asyncio
import json
import logging
import orjson
import sentry_sdk

from json import JSONDecodeError
from pydantic import Json
from typing import Any

from merino.providers.games.particle.backends.errors import (
    ParticleDeploymentError,
    ParticleFileManagerError,
)
from merino.providers.games.particle.backends.utils import GameFile
from merino.utils.gcs.gcs_uploader import GcsUploader

logger = logging.getLogger(__name__)


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
    green_deployment_folder: str
    manifest_file_name: str

    def __init__(
        self,
        gcs_client: GcsUploader,
        green_deployment_folder: str,
        manifest_file_name: str,
    ) -> None:
        """Initialize the remote filemanager."""
        self.gcs_client = gcs_client
        self.green_deployment_folder = green_deployment_folder
        self.manifest_file_name = manifest_file_name

    def get_manifest_file(self) -> dict[str, Any] | None:
        """Read remote manifest file from GCS.

        Raises:
            ParticleFileManagerError: If the manifest file cannot be accessed or cannot be converted to JSON.
        Returns:
            Dictionary containing manifest.
        """
        manifest: dict[str, Any] | None = None

        try:
            blob = self.gcs_client.get_file_by_name(self.manifest_file_name)

            if blob is not None:
                blob_data = blob.download_as_text()
                file_contents: dict = json.loads(blob_data)
                logger.info("Successfully loaded remote Particle manifest file.")

                manifest = file_contents
        except Exception as ex:
            error_msg = f"Error retrieving GCS manifest file. {ex}"
            logger.error(error_msg)
            sentry_sdk.capture_exception(ex)

            raise ParticleFileManagerError(error_msg) from ex

        # return json, or None if the blob wasn't found in GCS (cold start)
        return manifest

    async def upload_file(self, file_name: str, file_path: str, content_type: str) -> str:
        """Attempt to upload a file from the local filesystem to GCS. Overwrites an existing file."""
        blob_name = ""

        try:
            # wrap the call in an async thread to unblock other processing
            blob = await asyncio.to_thread(
                self.gcs_client.upload_from_filename,
                file_path=file_path,
                destination_name=f"{self.green_deployment_folder}/{file_name}",
                content_type=content_type,
                forced_upload=True,  # force an overwrite if necessary
            )

            if blob:
                blob_name = str(blob.name)

            return blob_name
        except Exception as ex:
            sentry_sdk.capture_exception(ParticleFileManagerError(str(ex)))
            return ""

    async def upload_manifest(self, manifest: Json) -> bool:
        """Upload manifest JSON to GCS. Overwrites the existing manifest file."""
        file_bytes = orjson.dumps(manifest)

        blob = await asyncio.to_thread(
            self.gcs_client.upload_content,
            content=file_bytes,
            destination_name=self.manifest_file_name,
            content_type="application/json",
            forced_upload=True,
        )

        # if the blob doesn't have an id (meaning it wasn't actually uploaded),
        # the process failed
        if not blob.id:
            sentry_sdk.capture_exception(
                ParticleFileManagerError("Error updating the manifest JSON in GCS.")
            )
            return False

        return True

    async def empty_staging_folder(self, files: list[GameFile]) -> None:
        """Delete uploaded files in the GCS staging folder. Used when a channel staging deployment fails midway, e.g. due to SHA validation or upload failure."""
        uploaded_files = [f for f in files if f.uploaded and hasattr(f, "gcs_staging_name")]

        for f in uploaded_files:
            try:
                await asyncio.to_thread(self.gcs_client.delete_file_by_name, f.gcs_staging_name)
            except Exception as ex:
                sentry_sdk.capture_exception(ParticleFileManagerError(str(ex)))

    async def deploy_staged_files(self, files: list[GameFile]) -> bool:
        """Move files from staging GCS 'folder'/name to 'production'/GCS root."""
        success = True

        for f in files:
            # one bit of special casing - force the entry point to the particle
            # application to be 'index.html' (in the root) to keep the endpoint
            # URL consistent.
            # this does assume there is only one HTML file for particle, which
            # is confirmed to be the case.
            destination_name = "index.html" if f.name.lower().endswith(".html") else f.remote_path

            try:
                await asyncio.to_thread(
                    self.gcs_client.move_file, f.gcs_staging_name, destination_name
                )
            except Exception as ex:
                # this exception should be treated as critical, as the game may
                # be in a broken state. sentry should be configured to alert to
                # slack on every error captured here.
                sentry_sdk.capture_exception(ParticleDeploymentError(str(ex)))

                # mark the process as a failure if any file move fails
                success = False

        return success

    async def delete_file(self, file_name: str) -> None:
        """Delete the given file from GCS."""
        try:
            await asyncio.to_thread(self.gcs_client.delete_file_by_name, file_name)
        except Exception as ex:
            sentry_sdk.capture_exception(ParticleFileManagerError(str(ex)))
