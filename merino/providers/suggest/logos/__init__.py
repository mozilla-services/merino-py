"""Logos provider"""

from timeit import default_timer as timer
import logging

from merino.utils import metrics
from merino.utils.storage import get_storage_client
from merino.utils.synced_gcs_blob_v2 import typed_gcs_json_blob_factory
from merino.providers.suggest.logos.provider import Provider, LogoManifest
from merino.configs import settings


logger = logging.getLogger(__name__)

provider: Provider | None = None
cron_interval_sec: int = settings.logos.cron_interval_sec
logos_manifest_key: str = settings.logos.logos_manifest_key
images_bucket: str = settings.image_gcs_v2.gcs_bucket


async def init_provider() -> None:
    """Initialize logos provider.

    This should only be called once at the startup of application.
    """
    global provider
    start = timer()

    logo_manifest = typed_gcs_json_blob_factory(
        LogoManifest,
        storage_client=get_storage_client(),
        metrics_client=metrics.get_metrics_client(),
        bucket_name=images_bucket,
        blob_name=logos_manifest_key,
        max_size=None,
        cron_interval_seconds=cron_interval_sec,
        cron_job_name="logo_manifest_sync",
    )

    provider = Provider(metrics_client=metrics.get_metrics_client(), logo_manifest=logo_manifest)
    provider.initialize()

    logger.info(
        "Logos provider initialization completed",
        extra={"provider": "logos", "elapsed": timer() - start},
    )


def get_provider() -> Provider:
    """Return logos provider."""
    if provider is None:
        raise ValueError("Logos provider has not been initialized.")
    return provider
