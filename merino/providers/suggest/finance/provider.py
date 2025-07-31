"""Finance integration."""

import asyncio
import logging
import time

import aiodogstatsd
from fastapi import HTTPException
from pydantic import HttpUrl

from merino.providers.suggest.base import BaseProvider, BaseSuggestion, SuggestionRequest
from merino.providers.suggest.custom_details import CustomDetails, PolygonDetails
from merino.providers.suggest.finance.backends.protocol import (
    FinanceBackend,
    FinanceBackendError,
    FinanceManifest,
    GetManifestResultCode,
    TickerSummary,
)
from merino.providers.suggest.finance.backends.polygon.utils import is_valid_ticker
from merino.utils import cron

logger = logging.getLogger(__name__)


class Provider(BaseProvider):
    """Suggestion provider for finance."""

    backend: FinanceBackend
    manifest_data: FinanceManifest | None
    metrics_client: aiodogstatsd.Client
    score: float
    url: HttpUrl
    cron_task_fetch: asyncio.Task
    cron_task_upload: asyncio.Task
    resync_interval_sec: int
    cron_interval_sec: int
    last_fetch_at: float

    def __init__(
        self,
        backend: FinanceBackend,
        metrics_client: aiodogstatsd.Client,
        score: float,
        name: str,
        query_timeout_sec: float,
        resync_interval_sec: int,
        cron_interval_sec: int,
        enabled_by_default: bool = False,
    ) -> None:
        self.backend = backend
        self.metrics_client = metrics_client
        self.score = score
        self._name = name
        self._query_timeout_sec = query_timeout_sec
        self._enabled_by_default = enabled_by_default
        self.url = HttpUrl("https://merino.services.mozilla.com/")
        self.manifest_data = FinanceManifest(tickers={})
        self.data_fetched_event = asyncio.Event()
        self.resync_interval_sec = resync_interval_sec
        self.cron_interval_sec = cron_interval_sec
        self.last_fetch_at = 0.0

        super().__init__()

    async def initialize(self) -> None:
        """Initialize the provider."""
        await self._fetch_manifest()

        cron_job_fetch = cron.Job(
            name="fetch_polygon_manifest",
            interval=self.cron_interval_sec,
            condition=self._should_fetch,
            task=self._fetch_manifest,
        )

        cron_job_upload = cron.Job(
            name="upload_polygon_manifest",
            interval=self.cron_interval_sec,
            condition=self._should_fetch,
            task=self._upload_manifest,
        )
        self.cron_task_fetch = asyncio.create_task(cron_job_fetch())
        self.cron_task_upload = asyncio.create_task(cron_job_upload())

    async def _fetch_manifest(self) -> None:
        """Cron fetch method to re-run after set interval.
        Does not set manifest_data if non-success code passed with None.
        """
        try:
            result_code, data = await self.backend.fetch_manifest_data()

            match GetManifestResultCode(result_code):
                case GetManifestResultCode.SUCCESS if data is not None:
                    self.manifest_data = data
                case GetManifestResultCode.FAIL:
                    logger.error("Failed to fetch manifest data from finance backend.")
                    return None
        except FinanceBackendError as err:
            logger.error("Failed to fetch manifest data from finance backend: %s", err)
        except Exception as e:
            logger.exception(f"Unexpected error in cron job 'fetch_manifest': {e}")

        finally:
            self.last_fetch_at = time.time()
            self.data_fetched_event.set()

    async def _upload_manifest(self) -> None:
        """Cron method to upload/update ticker images on GCS. Re-runs after set interval"""
        try:
            await self.backend.build_and_upload_manifest_file()
        except FinanceBackendError as err:
            logger.error("Failed to upload manifest data from finance backend: %s", err)
        except Exception as e:
            logger.exception(f"Unexpected error in cron job 'upload_manifest': {e}")
        finally:
            self.last_fetch_at = time.time()

    def _should_fetch(self) -> bool:
        """Determine if we should fetch new data based on time elapsed."""
        return (time.time() - self.last_fetch_at) >= self.resync_interval_sec

    def validate(self, srequest: SuggestionRequest) -> None:
        """Validate the suggestion request."""
        if not srequest.query:
            raise HTTPException(
                status_code=400,
                detail="Invalid query parameters: `q` is missing",
            )

    async def query(self, srequest: SuggestionRequest) -> list[BaseSuggestion]:
        """Provide finance suggestions."""
        # get a stock snapshot if the query param contains a supported ticker else do a search for that ticker
        try:
            if not is_valid_ticker(srequest.query):
                return []
            else:
                # Normalize the ticker to upper case since all downstream methods rely on it being upper case.
                ticker = srequest.query.upper()
                ticker_summary: TickerSummary | None
                image_url = self.get_image_url_for_ticker(ticker)

                if (
                    ticker_summary := await self.backend.get_ticker_summary(ticker, image_url)
                ) is None:
                    return []
                else:
                    return [self.build_suggestion(ticker_summary)]

        except Exception as e:
            logger.warning(f"Exception occurred for Polygon provider: {e}")
            return []

    def build_suggestion(self, data: TickerSummary) -> BaseSuggestion:
        """Build the suggestion with custom polygon details since this is a finance suggestion."""
        custom_details = CustomDetails(polygon=PolygonDetails(values=[data]))

        return BaseSuggestion(
            title="Finance Suggestion",
            url=HttpUrl(self.url),
            provider=self.name,
            is_sponsored=False,
            score=self.score,
            custom_details=custom_details,
        )

    def get_image_url_for_ticker(self, ticker: str) -> HttpUrl | None:
        """Return the GCS url from the manifest for a given ticker symbol"""
        if self.manifest_data:
            image_url = self.manifest_data.tickers.get(ticker.upper(), None)
            if image_url:
                return image_url
        return None

    async def shutdown(self) -> None:
        """Shut down the provider."""
        await self.backend.shutdown()
