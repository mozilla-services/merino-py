"""Initialize game providers."""

from merino.configs import settings

from merino.providers.games.particle.backends.particle import ParticleBackend
from merino.providers.games.particle.provider import Provider

from merino.utils.gcs.gcs_uploader import GcsUploader
from merino.utils.metrics import get_metrics_client

_particle_provider: Provider

# Module-level variables as looking up from settings each time is expensive.
_gcs_project = settings.games_particle_gcs.gcs_project
_gcs_bucket = settings.games_particle_gcs.gcs_bucket
_gcs_cdn_hostname = settings.games_particle_gcs.cdn_hostname


async def init_providers() -> None:
    """Initialize games providers - currently only Particle"""
    global _particle_provider

    gcs_uploader = GcsUploader(
        _gcs_project,
        _gcs_bucket,
        _gcs_cdn_hostname,
    )
    metrics_client = get_metrics_client()

    particle_backend = ParticleBackend(gcs_uploader=gcs_uploader, metrics_client=metrics_client)

    _particle_provider = Provider(
        backend=particle_backend, metrics_client=metrics_client, name="Particle Provider"
    )

    await _particle_provider.initialize()


def get_particle_provider() -> Provider:
    """Return the provider for the Particle game"""
    global _particle_provider
    return _particle_provider
