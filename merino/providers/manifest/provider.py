"""Provider for the Manifest data, fetched from GCS asynchronously and stored in memory."""

import asyncio
import time
import logging

import aiodogstatsd
import tldextract
from pydantic import HttpUrl, ValidationError

from merino.providers.manifest.backends.filemanager import GetManifestResultCode
from merino.utils import cron
from merino.utils.metrics import get_metrics_client

from merino.providers.manifest.backends.protocol import (
    ManifestBackend,
    ManifestBackendError,
    ManifestData,
)
from merino.configs import settings

logger = logging.getLogger(__name__)


class Provider:
    """Provide access to in-memory manifest data fetched from GCS."""

    manifest_data: ManifestData | None
    domain_lookup_table: dict[str, int]
    cron_task: asyncio.Task
    resync_interval_sec: int
    cron_interval_sec: int
    last_fetch_at: float
    name: str
    metrics_client: aiodogstatsd.Client

    def __init__(
        self,
        backend: ManifestBackend,
        resync_interval_sec: int,
        cron_interval_sec: int,
        name: str = "manifest",
    ) -> None:
        self.backend = backend
        self.name = name
        self.resync_interval_sec = resync_interval_sec
        self.cron_interval_sec = cron_interval_sec
        self.last_fetch_at = 0.0
        self.manifest_data = ManifestData(domains=[], partners=[])
        self.domain_lookup_table = {}
        self.data_fetched_event = asyncio.Event()
        self.metrics_client = get_metrics_client()

        super().__init__()

    async def initialize(self) -> None:
        """Initialize Manifest provider."""
        if settings.image_gcs.gcs_enabled:
            await self._fetch_data()

            cron_job = cron.Job(
                name="resync_manifest",
                interval=self.cron_interval_sec,
                condition=self._should_fetch,
                task=self._fetch_data,
            )
            self.cron_task = asyncio.create_task(cron_job())

    async def _fetch_data(self) -> None:
        """Cron fetch method to re-run after set interval.
        Does not set manifest_data if non-success code passed with None.
        """
        try:
            result_code, data = await self.backend.fetch()

            match GetManifestResultCode(result_code):
                case GetManifestResultCode.SUCCESS if data is not None:
                    self.manifest_data = data
                    self.domain_lookup_table = {
                        self._extract_full_domain(str(domain.url)): idx
                        for idx, domain in enumerate(data.domains)
                    }
                    self.last_fetch_at = time.time()

                case GetManifestResultCode.FAIL:
                    logger.error("Failed to fetch data from Manifest backend.")
                    return None
        except ManifestBackendError as err:
            logger.error("Failed to fetch data from Manifest backend: %s", err)

        finally:
            self.data_fetched_event.set()

    def _should_fetch(self) -> bool:
        """Determine if we should fetch new data based on time elapsed."""
        return (time.time() - self.last_fetch_at) >= self.resync_interval_sec

    def get_manifest_data(self) -> ManifestData | None:
        """Return manifest data"""
        return self.manifest_data

    def get_icon_url(self, url: str | HttpUrl) -> HttpUrl | None:
        """Get icon URL for a URL.

        Args:
            url: Full URL to look up (string or HttpUrl)

        Returns:
            Icon URL if found, None otherwise
        """
        try:
            url_str = str(url)
            input_full_domain = self._extract_full_domain(url_str)

            # Look for exact full domain match
            idx = self.domain_lookup_table.get(input_full_domain, -1)

            if idx >= 0 and self.manifest_data is not None:
                icon_url = self.manifest_data.domains[idx].icon
                try:
                    return HttpUrl(icon_url)
                except ValidationError:
                    domain_for_metrics = tldextract.extract(url_str).domain
                    self.metrics_client.increment(
                        "manifest.invalid_icon_url", tags={"domain": domain_for_metrics}
                    )
        except Exception as e:
            logger.warning(f"Error getting icon for URL {url}: {e}")
        return None

    def _extract_full_domain(self, url: str) -> str:
        """Extract the normalized domain (domain.tld) from a URL.

        Ignores:
        - Protocol (http/https)
        - www subdomain
        - Paths, query params, etc.

        Examples:
        - https://www.google.com -> google.com
        - http://www.bbc.co.uk/news -> bbc.co.uk
        - https://go.abc.com -> go.abc.com
        - https://businessinsider.es -> businessinsider.es
        """
        extracted = tldextract.extract(url)

        # Ignore 'www' subdomain, but keep other subdomains
        subdomain = extracted.subdomain if extracted.subdomain != "www" else ""

        parts = [subdomain, extracted.domain, extracted.suffix]
        # Filter out empty parts and join with dots
        return ".".join(part for part in parts if part)
