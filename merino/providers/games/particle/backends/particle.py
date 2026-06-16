"""Particle game backend."""

import aiodogstatsd
import asyncio
import logging
import orjson
import sentry_sdk
import tempfile

from httpx import AsyncClient, HTTPError, Response
from pydantic import Json

from merino.configs import settings
from merino.providers.games.particle.backends.protocol import Particle
from merino.providers.games.particle.backends.errors import ParticleRemoteFileProcessError
from merino.providers.games.particle.backends.filemanager import ParticleRemoteFileManager
from merino.providers.games.particle.backends.utils import (
    download_remote_file,
    GameFile,
    get_files_from_manifest_for_channel,
    RemoteChannelEnum,
    remote_manifest_channel_is_updated,
)
from merino.utils.gcs.gcs_uploader import GcsUploader

logger = logging.getLogger(__name__)

# Module-level variable as retrieving from settings each time is expensive.
_game_url = settings.games_providers.particle.game_url


class ParticleBackend:
    """Backend for managing and returning Particle game data."""

    gcs_uploader: GcsUploader
    http_client: AsyncClient
    metrics_client: aiodogstatsd.Client
    # remote endpoint
    particle_url_root: str
    # path to the manifest on the remote endpoint
    particle_url_path_manifest: str
    # manages files stored in GCS
    remote_file_manager: ParticleRemoteFileManager

    def __init__(
        self,
        gcs_uploader: GcsUploader,
        http_client: AsyncClient,
        metrics_client: aiodogstatsd.Client,
        particle_url_root: str,
        particle_url_path_manifest: str,
        remote_file_manager: ParticleRemoteFileManager,
    ) -> None:
        """Initialize the Particle backend."""
        self.gcs_uploader = gcs_uploader
        self.http_client = http_client
        self.metrics_client = metrics_client
        self.particle_url_root = particle_url_root
        self.particle_url_path_manifest = particle_url_path_manifest
        self.remote_file_manager = remote_file_manager

    async def get_game_url(self) -> Particle | None:
        """Return the public URL for the Particle game"""
        return Particle(url=_game_url)

    async def fetch_manifest_json_from_remote(self) -> Json | None:
        """Retrieve the latest manifest JSON from Particle"""
        manifest: Response | None = None
        manifest_json: Json | None = None

        # try to get the manifest from the internet
        try:
            manifest = await self.http_client.get(
                f"{self.particle_url_root}{self.particle_url_path_manifest}"
            )

            manifest.raise_for_status()
        except HTTPError as ex:
            error_msg = f"HTTP error when fetching Particle manifest: {ex}"

            logger.error(error_msg)

            sentry_sdk.capture_exception(ex)

        # if the manifest was retrieved and has a content property, we're good
        if manifest and manifest.content:
            # try to convert the contents of manifest.content to JSON
            try:
                manifest_json = orjson.loads(manifest.content)
            except ValueError as ex:
                error_msg = "JSON error when converting Particle response"

                logger.error(error_msg)

                sentry_sdk.capture_exception(ex)

        # returning json or None
        return manifest_json

    async def fetch_manifest_json_from_gcs(self) -> Json | None:
        """Retrieve the manifest json last stored in GCS"""
        # the gcp client library is synchronous - wrap in an async thread so
        # we don't block processing
        return await asyncio.to_thread(self.remote_file_manager.get_manifest_file)

    async def update_channel_files(
        self, manifest_remote: Json, manifest_gcs: Json, channel: RemoteChannelEnum
    ) -> bool:
        """Attempt to update files for the given channel."""
        if remote_manifest_channel_is_updated(manifest_remote, manifest_gcs, channel):
            # get the files for the given channel from the remote manifest
            files: list[GameFile] = get_files_from_manifest_for_channel(manifest_remote, channel)

            # steps necessary for the process to be considered a success
            staged = False
            deployed = False

            if not len(files):
                # if no files were found, exit early
                sentry_sdk.capture_exception(
                    ParticleRemoteFileProcessError(
                        f"No files found in remote manifest for {channel} channel."
                    )
                )
                return False
            else:
                # download the remote files, verify their SHAs, and upload to GCS
                staged, files = await self.stage_channel_files(files=files)

                if staged:
                    # if staging was successful, attempt to deploy the channel
                    deployed = await self.deploy_channel_files(
                        files, manifest_remote=manifest_remote
                    )

                    if deployed:
                        await self.cleanup_old_files_for_channel(
                            manifest_remote=manifest_remote,
                            manifest_gcs=manifest_gcs,
                            channel=channel,
                        )

                # if staging and deploying succeeded, the process was a success
                return staged and deployed
        else:
            # if the channel files don't need to be updated, return False
            return False

    async def stage_channel_files(self, files: list[GameFile]) -> tuple[bool, list[GameFile]]:
        """Orchestration function to download remote files for the given channel to a temporary directory,
        verify their SHAs, and, if valid, upload them to GCS. If one file fails, we cancel the rest of the checks, as all files in a set must
        validate and upload successfully.

        This will prepare the channel to be "deployed".

        Returns overall success status and the list of GameFiles with their verified/uploaded statuses updated.
        """
        # create a temporary directory to store remote files.
        # at the end of this context, the temp dir will be automatically deleted.
        with tempfile.TemporaryDirectory() as tmpdir_name:
            for file in files:
                # where to store the remote file locally in the context's tempdir
                file.local_path = f"{tmpdir_name}/{file.name}"

                # attempt to download the file into the temp directory
                try:
                    download_remote_file(
                        f"{self.particle_url_root}/{file.remote_path}", file.local_path
                    )
                except Exception as ex:
                    # capture any exceptions during download and stop processing the manifest files
                    sentry_sdk.capture_exception(ParticleRemoteFileProcessError(str(ex)))
                    break

                # validate the SHA of each file
                file.sha_computed = GameFile.compute_sha(file.local_path)

                if file.sha_target != file.sha_computed:
                    sentry_sdk.capture_exception(
                        ParticleRemoteFileProcessError("File SHA mismatch")
                    )
                    break

                # if all the above succeeds, the file is considered verified
                file.sha_verified = True

                # attempt to upload file to GCS - will return the name of the
                # remote file if successful, an empty string on failure.
                # note - for the file_name, we pass in file.remote path, e.g.
                # assets/style-SOMEHASH.css, so directory information is
                # retained in GCS.
                file.gcs_staging_name = await self.remote_file_manager.upload_file(
                    file_name=file.remote_path,
                    file_path=file.local_path,
                    content_type=file.content_type,
                )

                if file.gcs_staging_name:
                    file.uploaded = True
                else:
                    break

        # if some files were uploaded but not all, erase the partial green deployment
        # by clearing out the GCS "green" folder
        if any(f.uploaded for f in files) and not all(f.uploaded for f in files):
            await self.remote_file_manager.empty_staging_folder(files=files)

        # return set of files with sha_verified and uploaded properties
        # (potentially) updated
        return all(f.sha_verified and f.uploaded for f in files), files

    async def deploy_channel_files(self, files: list[GameFile], manifest_remote: Json) -> bool:
        """Deploy files from the 'green' folder in GCS to the root."""
        # "move" staging files to GCS bucket root
        # (this is really just a renaming of files)
        # exceptions will be captured and sent to sentry
        deploy_success = await self.remote_file_manager.deploy_staged_files(files)

        # overwrite GCS manifest JSON with latest from particle remote
        upload_manifest_success = False

        if deploy_success:
            upload_manifest_success = await self.remote_file_manager.upload_manifest(
                manifest_remote
            )

        # if all the above succeeds, the deploy was successful
        return deploy_success and upload_manifest_success

    async def cleanup_old_files_for_channel(
        self, manifest_remote: Json, manifest_gcs: Json, channel: RemoteChannelEnum
    ) -> bool:
        """Clean up any outdated files for the given channel. Run after a channel deploy has succeeded."""
        # stub
        return True
