"""Logos provider"""

from timeit import default_timer as timer
import logging

from gcloud.aio.storage import Storage

from merino.utils import metrics
from merino.providers.suggest.logos.provider import Provider

logger = logging.getLogger(__name__)

provider: Provider | None = None


async def init_provider() -> None:
    """Initialize logos provider.

    This should only be called once at the startup of application.
    """
    global provider
    start = timer()

    provider = Provider(
        metrics_client=metrics.get_metrics_client(),
        storage_client=Storage(),
    )

    logger.info(
        "Logos provider initialization completed",
        extra={"provider": "logos", "elapsed": timer() - start},
    )


def get_provider() -> Provider:
    """Return logos provider."""
    if provider is None:
        raise ValueError("Logos provider has not been initialized.")
    return provider
