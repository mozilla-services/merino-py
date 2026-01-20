"""Finance integration."""

import asyncio
import logging
import time

import aiodogstatsd
from fastapi import HTTPException
from pydantic import HttpUrl

from merino.providers.suggest.base import (
    BaseProvider,
    BaseSuggestion,
    SuggestionRequest,
)
from merino.providers.suggest.custom_details import CustomDetails, MassiveDetails
from merino.providers.suggest.finance.backends.protocol import (
    FinanceBackend,
    FinanceBackendError,
    FinanceManifest,
    GetManifestResultCode,
    TickerSummary,
)
from merino.providers.suggest.finance.backends.massive.utils import (
    get_tickers_for_query,
)
from merino.utils import cron
from merino.configs import settings

logger = logging.getLogger(__name__)


class Provider(BaseProvider):
    """Suggestion provider for finance."""

    backend: FinanceBackend
    manifest_data: FinanceManifest | None
    metrics_client: aiodogstatsd.Client
    score: float
    url: HttpUrl
    cron_task_fetch: asyncio.Task
    resync_interval_sec: int
    cron_interval_sec: int
    last_fetch_at: float
    last_fetch_failure_at: float | None = None

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
        if settings.image_gcs.gcs_enabled:
            await self._fetch_manifest()

            cron_job_fetch = cron.Job(
                name="fetch_massive_manifest",
                interval=self.cron_interval_sec,
                condition=self._should_fetch,
                task=self._fetch_manifest,
            )

            self.cron_task_fetch = asyncio.create_task(cron_job_fetch())

    async def _fetch_manifest(self) -> None:
        """Cron fetch method to re-run after set interval.
        Does not set manifest_data if non-success code passed with None.
        """
        try:
            result_code, data = await self.backend.fetch_manifest_data()

            match GetManifestResultCode(result_code):
                case GetManifestResultCode.SUCCESS if data is not None:
                    self.manifest_data = data
                    self.last_fetch_at = time.time()
                    self.last_fetch_failure_at = None

                case GetManifestResultCode.FAIL:
                    logger.error("Failed to fetch manifest data from finance backend.")
                    self.last_fetch_failure_at = time.time()
                    return None

        except FinanceBackendError as err:
            logger.error("Failed to fetch manifest data from finance backend: %s", err)
            self.last_fetch_failure_at = time.time()
            return None

        except Exception as e:
            logger.exception(f"Unexpected error in cron job 'fetch_manifest': {e}")
            self.last_fetch_failure_at = time.time()
            return None

        finally:
            self.data_fetched_event.set()

    def _should_fetch(self) -> bool:
        """Determine if we should fetch new data based on time and last failure."""
        now = time.time()

        # If we had a failure recently, wait at least 2 hours before retrying
        if self.last_fetch_failure_at and (now - self.last_fetch_failure_at) < 7200:
            logger.info("Skipping fetch: last failure was less than an hour ago.")
            return False

        return (now - self.last_fetch_at) >= self.resync_interval_sec

    def validate(self, srequest: SuggestionRequest) -> None:
        """Validate the suggestion request."""
        if not srequest.query:
            raise HTTPException(
                status_code=400,
                detail="Invalid query parameters: `q` is missing",
            )

    def normalize_query(self, query: str) -> str:
        """Remove trailing spaces from the query string and support both $(stock) and $ (stock)"""
        return query.strip().replace("$", "STOCK ").replace("  ", " ")

    async def query(self, srequest: SuggestionRequest) -> list[BaseSuggestion]:
        """Provide finance suggestions."""
        # Get the list of tickers (0 to 3) for the query string.
        tickers = get_tickers_for_query(srequest.query)

        try:
            if not tickers:
                return []
            else:
                with self.metrics_client.timeit("polygon.provider.query.latency"):
                    ticker_summaries: list[TickerSummary] = []
                    # Get snapshots for the extracted tickers. Can return 0 to 3 snapshots.
                    ticker_snapshots = await self.backend.get_snapshots(tickers)

                    # Build ticker summary for each snapshot and its ticker's image
                    for snapshot in ticker_snapshots:
                        image_url = self.get_image_url_for_ticker(snapshot.ticker)
                        ticker_summaries.append(
                            self.backend.get_ticker_summary(snapshot, image_url)
                        )

                    return [self.build_suggestion(ticker_summaries)]

        except Exception as e:
            logger.warning(f"Exception occurred for Massive provider: {e}")
            return []

    def build_suggestion(self, data: list[TickerSummary]) -> BaseSuggestion:
        """Build the suggestion with custom massive details since this is a finance suggestion."""
        custom_details = CustomDetails(massive=MassiveDetails(values=data))

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
        return self.manifest_data.tickers.get(ticker.upper()) if self.manifest_data else None

    async def shutdown(self) -> None:
        """Shut down the provider."""
        await self.backend.shutdown()
