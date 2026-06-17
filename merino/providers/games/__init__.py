"""Initialize game providers."""

import pathlib

from merino.configs import settings
from merino.providers.games.particle.backends.filemanager import (
    ParticleLocalFileManager,
    ParticleRemoteFileManager,
)
from merino.providers.games.particle.backends.particle import ParticleBackend
from merino.providers.games.particle.provider import Provider

from merino.utils.gcs.gcs_uploader import GcsUploader
from merino.utils.http_client import create_http_client
from merino.utils.metrics import get_metrics_client

# get the application working directory to retrieve local manifest schema file
_app_root_dir: str = str(pathlib.Path.cwd())

_particle_provider: Provider | None = None

# Module-level variables as looking up from settings each time is expensive.
_connect_timeout = settings.games_providers.particle.connect_timeout_sec
_enabled = settings.games_providers.particle.enabled
_gcs_project = settings.games_particle_gcs.gcs_project
_gcs_bucket = settings.games_particle_gcs.gcs_bucket
_gcs_cdn_hostname = settings.games_particle_gcs.cdn_hostname
_gcs_green_deployment_folder = settings.games_particle_gcs.green_deployment_folder
_manifest_gcs_file_name = settings.games_providers.particle.manifest_gcs_file_name
_manifest_schema_file_path = (
    f"{_app_root_dir}/{settings.games_providers.particle.manifest_schema_file_path}"
)
_manifest_schema_version = settings.games_providers.particle.manifest_schema_version
_url_root = settings.games_providers.particle.url_root
_url_path_manifest = settings.games_providers.particle.url_path_manifest


async def init_providers() -> None:
    """Initialize games providers - currently only Particle"""
    init_particle()


def init_particle() -> None:
    """Initialize the Particle provider."""
    global _particle_provider

    gcs_uploader = GcsUploader(
        _gcs_project,
        _gcs_bucket,
        _gcs_cdn_hostname,
    )

    http_client = create_http_client(connect_timeout=_connect_timeout)

    metrics_client = get_metrics_client()

    # manages retrieving local manifest schema validation file
    local_file_manager = ParticleLocalFileManager(_manifest_schema_file_path)

    # manages particle files in gcs
    remote_file_manager = ParticleRemoteFileManager(
        gcs_client=gcs_uploader,
        manifest_file_name=_manifest_gcs_file_name,
        green_deployment_folder=_gcs_green_deployment_folder,
    )

    particle_backend = ParticleBackend(
        gcs_uploader=gcs_uploader,
        http_client=http_client,
        metrics_client=metrics_client,
        particle_url_root=_url_root,
        particle_url_path_manifest=_url_path_manifest,
        remote_file_manager=remote_file_manager,
    )

    _particle_provider = Provider(
        backend=particle_backend,
        manifest_schema=local_file_manager.get_manifest_schema(),
        manifest_schema_version=_manifest_schema_version,
        metrics_client=metrics_client,
        name="Particle Provider",
        enabled=_enabled,
    )

    _particle_provider.initialize()


def get_particle_provider() -> Provider:
    """Return the provider for the Particle game"""
    if _particle_provider is None:
        raise ValueError("Particle provider has not been initialized.")

    return _particle_provider
