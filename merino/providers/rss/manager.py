"""RSS provider manager."""

from enum import Enum, unique

from dynaconf.base import Settings

from merino.configs import settings
from merino.utils.http_client import create_http_client
from merino.utils.gcs.gcs_uploader import GcsUploader
from merino.providers.rss.base import BaseRssProvider
from merino.providers.rss.wikimedia_potd.backends.wikimedia_potd import (
    WikimediaPotdBackend,
)
from merino.providers.rss.wikimedia_potd.provider import WikimediaPotdProvider
from merino.utils.metrics import get_metrics_client


@unique
class RssProviderType(str, Enum):
    """Enum for RSS provider type."""

    WIKIMEDIA_POTD = "wikimedia_potd"


def _create_provider(provider_id: str, setting: Settings) -> BaseRssProvider:
    """Create an RSS provider for a given type and settings.

    Exceptions:
      - `ValueError` if the provider type is unknown.
    """
    match setting.type:
        case RssProviderType.WIKIMEDIA_POTD:
            http_client = create_http_client(
                base_url=settings.rss_providers.wikimedia_potd.fed_url,
                connect_timeout=settings.rss_providers.wikimedia_potd.connect_timeout_sec,
            )

            return WikimediaPotdProvider(
                backend=WikimediaPotdBackend(
                    feed_url=setting.feed_url,
                    gcs_uploader=GcsUploader(
                        settings.image_gcs.gcs_project,
                        settings.image_gcs.gcs_bucket,
                        settings.image_gcs.cdn_hostname,
                    ),
                    http_client=http_client,
                    metrics_client=get_metrics_client(),
                ),
                metrics_client=get_metrics_client(),
                name=provider_id,
                query_timeout_sec=setting.query_timeout_sec,
                enabled_by_default=setting.enabled_by_default,
            )
        case _:
            raise ValueError(f"Unknown RSS provider type: {setting.type}")


def load_providers() -> dict[str, BaseRssProvider]:
    """Load RSS providers from configuration."""
    providers: dict[str, BaseRssProvider] = {}
    for provider_id, setting in settings.rss_providers.items():
        providers[provider_id] = _create_provider(provider_id, setting)
    return providers
