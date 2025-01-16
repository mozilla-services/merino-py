"""Initialize Manifest Provider"""

from timeit import default_timer as timer
import logging
from merino.utils import metrics
from merino.providers.manifest.provider import Provider
from merino.providers.manifest.backends.manifest import ManifestBackend
from merino.configs import settings

logger = logging.getLogger(__name__)

provider: Provider | None = None


async def init_provider() -> None:
    """Initialize manifest provider

    This should only be called once at the startup of application.
    """
    global provider
    start = timer()

    provider = Provider(
        backend=ManifestBackend(),
        resync_interval_sec=settings.manifest.resync_interval_sec,
        cron_interval_sec=settings.manifest.cron_interval_sec,
    )

    # initialize provider and record time
    init_metric = "providers.initialize"
    client = metrics.get_metrics_client()
    with client.timeit(init_metric):
        client.timeit_task(provider.initialize(), "providers.initialize.manifest")

        logger.info(
            "Provider initialization completed",
            extra={"provider": "manifest", "elapsed": timer() - start},
        )


def get_provider() -> Provider:
    """Return manifest provider"""
    print(f"DEBUG: provider={provider}")
    if provider is None:
        raise ValueError("Provider has not been initialized.")
    return provider
