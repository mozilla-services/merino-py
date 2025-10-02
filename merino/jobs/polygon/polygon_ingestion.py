"""Downloads and uploads ticker images for polygon"""

from merino.cache.none import NoCacheAdapter
from merino.providers.suggest.finance.backends.polygon.backend import PolygonBackend
from merino.providers.suggest.finance.backends.protocol import FinanceBackend
from merino.providers.suggest.finance.provider import Provider
from merino.configs import settings
from merino.utils.metrics import get_metrics_client
from merino.utils.http_client import create_http_client
from merino.utils.gcs.gcs_uploader import GcsUploader

setting = settings.providers.polygon


class PolygonIngestion:
    """Class for managing the Polygon image ingestion pipeline"""

    provider: Provider

    def __init__(self):
        self.provider = self.get_provider()

    def get_provider(self) -> Provider:
        """Return a polygon provider instance"""
        provider = Provider(
            backend=PolygonBackend(
                api_key=settings.polygon.api_key,
                metrics_client=get_metrics_client(),
                metrics_sample_rate=settings.polygon.metrics_sampling_rate,
                http_client=create_http_client(
                    base_url=settings.polygon.url_base,
                    connect_timeout=settings.providers.polygon.connect_timeout_sec,
                ),
                url_param_api_key=settings.polygon.url_param_api_key,
                url_single_ticker_snapshot=settings.polygon.url_single_ticker_snapshot,
                url_single_ticker_overview=settings.polygon.url_single_ticker_overview,
                ticker_ttl_sec=settings.providers.polygon.cache_ttls.ticker_ttl_sec,
                gcs_uploader=GcsUploader(
                    settings.image_gcs.gcs_project,
                    settings.image_gcs.gcs_bucket,
                    settings.image_gcs.cdn_hostname,
                ),
                cache=NoCacheAdapter(),
            ),
            metrics_client=get_metrics_client(),
            score=setting.score,
            name="polygon",
            query_timeout_sec=setting.query_timeout_sec,
            enabled_by_default=setting.enabled_by_default,
            resync_interval_sec=setting.resync_interval_sec,
            cron_interval_sec=setting.cron_interval_sec,
        )

        return provider

    async def ingest(self) -> None:
        """Trigger the ingestion pipeline: download logos, upload them, and write manifest."""
        backend: FinanceBackend = self.provider.backend
        await backend.build_and_upload_manifest_file()
        await backend.shutdown()
