"""A wrapper for Polygon API interactions."""

import hashlib
import logging
import aiodogstatsd
from httpx import AsyncClient, Response, HTTPStatusError
from pydantic import HttpUrl, ValidationError
from merino.configs import settings
from typing import Any

from merino.providers.suggest.finance.backends.polygon.filemanager import PolygonFilemanager
from merino.providers.suggest.finance.backends.protocol import (
    FinanceBackend,
    FinanceManifest,
    GetManifestResultCode,
    TickerSnapshot,
    TickerSummary,
)
from merino.providers.suggest.finance.backends.polygon.utils import (
    TICKERS,
    extract_ticker_snapshot,
    build_ticker_summary,
)
from merino.utils.gcs.gcs_uploader import GcsUploader
from merino.utils.gcs.models import Image

# Export all the classes from this module
__all__ = [
    "PolygonBackend",
]

logger = logging.getLogger(__name__)

GCS_BLOB_NAME = "polygon_latest.json"


class PolygonBackend(FinanceBackend):
    """Backend that connects to the Polygon API."""

    api_key: str
    metrics_client: aiodogstatsd.Client
    http_client: AsyncClient
    metrics_sample_rate: float
    gcs_uploader: GcsUploader
    url_param_api_key: str
    url_single_ticker_snapshot: str
    url_single_ticker_overview: str
    filemanager: PolygonFilemanager

    def __init__(
        self,
        api_key: str,
        url_param_api_key: str,
        url_single_ticker_snapshot: str,
        url_single_ticker_overview: str,
        metrics_client: aiodogstatsd.Client,
        http_client: AsyncClient,
        gcs_uploader: GcsUploader,
        metrics_sample_rate: float,
    ) -> None:
        """Initialize the Polygon backend."""
        self.api_key = api_key
        self.metrics_client = metrics_client
        self.http_client = http_client
        self.metrics_sample_rate = metrics_sample_rate
        self.url_param_api_key = url_param_api_key
        self.gcs_uploader = gcs_uploader
        self.url_single_ticker_snapshot = url_single_ticker_snapshot
        self.url_single_ticker_overview = url_single_ticker_overview
        self.filemanager = PolygonFilemanager(
            gcs_bucket_path=settings.image_gcs.gcs_bucket,
            blob_name=GCS_BLOB_NAME,
        )

    async def get_ticker_summary(
        self, ticker: str, image_url: HttpUrl | None
    ) -> TickerSummary | None:
        """Get the ticker summary for the finance suggestion.
        This method first calls the fetch for snapshot method, extracts the ticker snapshot
        and builds the ticker summary.
        """
        snapshot: TickerSnapshot | None = extract_ticker_snapshot(
            await self.fetch_ticker_snapshot(ticker)
        )

        if snapshot is None:
            return None
        else:
            return build_ticker_summary(ticker=ticker, snapshot=snapshot, image_url=image_url)

    async def fetch_ticker_snapshot(self, ticker: str) -> Any | None:
        """Make a request and fetch the snapshot for this single ticker."""
        params = {self.url_param_api_key: self.api_key}

        try:
            response: Response = await self.http_client.get(
                self.url_single_ticker_snapshot.format(ticker=ticker), params=params
            )

            response.raise_for_status()
        except HTTPStatusError as ex:
            logger.error(
                f"Polygon request error for ticker snapshot: {ex.response.status_code} {ex.response.reason_phrase}"
            )
            return None

        return response.json()

    async def get_ticker_image_url(self, ticker: str) -> str | None:
        """Get the logo URL for the ticker (requires API key when fetching)"""
        params = {self.url_param_api_key: self.api_key}

        try:
            response: Response = await self.http_client.get(
                self.url_single_ticker_overview.format(ticker=ticker), params=params
            )
            response.raise_for_status()
            result = response.json()
        except HTTPStatusError as ex:
            logger.error(
                f"Failed to get ticker image for {ticker}: {ex.response.status_code} {ex.response.reason_phrase}"
            )
            return None

        branding = result.get("results", {}).get("branding", {})
        image_url = branding.get("logo_url")

        if isinstance(image_url, str):
            return image_url

        return None

    async def download_ticker_image(self, ticker: str) -> Image | None:
        """Download the image using the image URL.

        Returns an Image object containing the binary content and content type,
        or None if no image URL is found.
        """
        image_url = await self.get_ticker_image_url(ticker)
        if not image_url:
            return None

        params = {self.url_param_api_key: self.api_key}
        try:
            response: Response = await self.http_client.get(image_url, params=params)
            response.raise_for_status()

            content = response.content
            content_type = response.headers.get("Content-Type", "image/svg+xml")
            return Image(
                content=content,
                content_type=str(content_type),
            )
        except HTTPStatusError as ex:
            logger.error(
                f"Failed to download ticker image for {ticker}: {ex.response.status_code} {ex.response.reason_phrase}"
            )
            return None

    async def bulk_download_and_upload_ticker_images(
        self, tickers: list[str], prefix: str = "polygon"
    ) -> dict[str, str]:
        """Download and upload images for a list of ticker symbols.
        Uses content hash to deduplicate and skips upload if destination blob already exists.
        """
        uploaded_urls = {}

        for ticker in tickers:
            try:
                logo: Image | None = await self.download_ticker_image(ticker)

                if logo is None:
                    logger.warning(f"No logo found for ticker {ticker}, skipping.")
                    continue

                content_hash = hashlib.sha256(logo.content).hexdigest()
                content_len = len(logo.content)

                destination_name = f"{prefix}/{content_hash}_{content_len}.svg"

                try:
                    public_url = self.gcs_uploader.upload_image(
                        image=logo,
                        destination_name=destination_name,
                        forced_upload=False,
                    )
                    uploaded_urls[ticker] = public_url

                except Exception as e:
                    logger.error(f"Failed to upload logo for {ticker}: {e}")
            except Exception as e:
                logger.error(f"Error processing ticker {ticker}: {e}")

        return uploaded_urls

    @staticmethod
    def build_finance_manifest(gcs_image_urls: dict[str, str]) -> FinanceManifest:
        """Build a FinanceManifest from ticker -> GCS image URL mappings."""
        manifest_dict = {}

        for ticker, url in gcs_image_urls.items():
            manifest_dict[ticker.upper()] = url

        try:
            return FinanceManifest(tickers=manifest_dict)
        except ValidationError as e:
            logger.error(f"Failed to build FinanceManifest due to validation error: {e}")
            return FinanceManifest(tickers={})

    async def fetch_manifest_data(self) -> tuple[GetManifestResultCode, FinanceManifest | None]:
        """Fetch manifest data from GCS through the filemanager."""
        return await self.filemanager.get_file()

    async def build_and_upload_manifest_file(self) -> None:
        """Build and upload the finance manifest file to GCS.

        - Downloads ticker logo images from polygon.
        - Uploads only new or changed images to GCS.
        - Constructs a FinanceManifest from the resulting GCS URLs.
        - Uploads the manifest JSON file to the GCS bucket.
        """
        try:
            url_map = await self.bulk_download_and_upload_ticker_images(list(TICKERS))

            manifest = self.build_finance_manifest(url_map)

            success = await self.filemanager.upload_file(manifest)
            if not success:
                logger.error("polygon manifest upload failed.")
        except Exception as e:
            logger.error(f"Error building/uploading manifest: {e}")

    async def shutdown(self) -> None:
        """Close http client and cache connections."""
        await self.http_client.aclose()
