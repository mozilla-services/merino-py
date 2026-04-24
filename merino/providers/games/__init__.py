"""Initialize game providers."""

from merino.configs import settings

from merino.providers.games.particle.backends.particle import ParticleBackend
from merino.providers.games.particle.provider import Provider

from merino.utils.gcs.gcs_uploader import GcsUploader
from merino.utils.http_client import create_http_client
from merino.utils.metrics import get_metrics_client

_particle_provider: Provider

# Module-level variables as looking up from settings each time is expensive.
_connect_timeout = settings.games_providers.particle.connect_timeout_sec
_gcs_project = settings.games_particle_gcs.gcs_project
_gcs_bucket = settings.games_particle_gcs.gcs_bucket
_gcs_cdn_hostname = settings.games_particle_gcs.cdn_hostname
_url_root = settings.games_providers.particle.url_root
_url_path_manifest = settings.games_providers.particle.url_path_manifest


async def init_providers() -> None:
    """Initialize games providers - currently only Particle"""
    global _particle_provider

    gcs_uploader = GcsUploader(
        _gcs_project,
        _gcs_bucket,
        _gcs_cdn_hostname,
    )

    http_client = create_http_client(connect_timeout=_connect_timeout)

    metrics_client = get_metrics_client()

    particle_backend = ParticleBackend(
        gcs_uploader=gcs_uploader,
        http_client=http_client,
        metrics_client=metrics_client,
        particle_url_root=_url_root,
        particle_url_path_manifest=_url_path_manifest,
    )

    _particle_provider = Provider(
        backend=particle_backend, metrics_client=metrics_client, name="Particle Provider"
    )

    await _particle_provider.initialize()


def get_particle_provider() -> Provider:
    """Return the provider for the Particle game"""
    global _particle_provider
    return _particle_provider
