"""Protocol for finance provider backends."""

from enum import Enum
from typing import Any, Dict, Protocol
from pydantic import BaseModel, HttpUrl

from merino.exceptions import BackendError
from merino.utils.gcs.models import Image


class FinanceBackendError(BackendError):
    """Finance Specific Errors"""

    pass


class TickerSnapshot(BaseModel):
    """Ticker Snapshot."""

    todays_change_perc: str
    last_price: str


class TickerSummary(BaseModel):
    """Ticker summary."""

    ticker: str
    name: str
    last_price: str
    todays_change_perc: str
    query: str
    image_url: HttpUrl | None


class FinanceManifest(BaseModel):
    """Model for the manifest file content"""

    tickers: Dict[str, HttpUrl]


class GetManifestResultCode(Enum):
    """Enum to capture the result of getting manifest file."""

    SUCCESS = 0
    FAIL = 1


class FinanceBackend(Protocol):
    """Protocol for a finance backend that this provider depends on.

    Note: This only defines the methods used by the provider. The actual backend
    might define additional methods and attributes which this provider doesn't
    directly depend on.
    """

    async def get_ticker_summary(
        self, ticker: str, image_url: HttpUrl | None
    ) -> TickerSummary | None:  # pragma: no cover
        """Get snapshot info for a given ticker from partner.

        Raises:
            BackendError: Category of error specific to provider backends.
        """
        ...

    async def shutdown(self) -> None:  # pragma: no cover
        """Close down any open connections."""
        ...

    async def fetch_ticker_snapshot(self, ticker: str) -> Any | None:
        """Make a request and fetch the snapshot for this single ticker."""
        ...

    async def get_ticker_image_url(self, ticker) -> str | None:
        """Get the image URL for the ticker (requires API key when fetching)"""
        ...

    async def download_ticker_image(self, ticker: str) -> Image | None:
        """Download the image using the logo URL.

        Returns an Image object containing the binary content and content type,
        or None if no URL is found.
        """
        ...

    async def bulk_download_and_upload_ticker_images(
        self, tickers: list[str], prefix: str = "tickers"
    ) -> dict[str, str]:
        """Download and upload images for a list of ticker symbols.
        Uses content hash to deduplicate and skips upload if destination blob already exists.
        """
        ...

    @staticmethod
    def build_finance_manifest(gcs_image_urls: dict[str, str]) -> FinanceManifest:
        """Build a FinanceManifest from ticker -> GCS image URL mappings."""
        ...

    async def fetch_manifest_data(self) -> tuple[GetManifestResultCode, FinanceManifest | None]:
        """Fetch manifest data from GCS through the filemanager."""
        ...

    async def build_and_upload_manifest_file(self) -> None:
        """Build and upload the finance manifest file to GCS.

        This method:
        - Downloads ticker logo images from polygon.
        - Uploads only new or changed images to GCS.
        - Constructs a FinanceManifest from the resulting GCS URLs.
        - Uploads the manifest JSON file to the GCS bucket.
        """
        ...
