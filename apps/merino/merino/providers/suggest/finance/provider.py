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
from merino.providers.suggest.custom_details import CustomDetails, PolygonDetails
from merino.providers.suggest.finance.backends.protocol import (
    FinanceBackend,
    FinanceBackendError,
    FinanceManifest,
    GetManifestResultCode,
    TickerSummary,
)
from merino.providers.suggest.finance.backends.polygon.etf_ticker_company_mapping import (
    STOCKS_WIDGET_DEFAULT_ETFS,
)
from merino.providers.suggest.finance.backends.polygon.utils import (
    get_tickers_for_newtab_query,
    get_tickers_for_query,
)
from merino_common.utils import cron
from merino.configs import settings

logger = logging.getLogger(__name__)

# The `request_type` the stocks widget sends for its search pick-list.
TICKER_SEARCH_REQUEST_TYPE = "ticker_search"


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
                name="fetch_polygon_manifest",
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
        # newtab requests don't require a query string; an empty query returns the default ETF set.
        # A non-empty query is used to look up individual stocks regardless of source.
        if srequest.source != "newtab" and not srequest.query:
            raise HTTPException(
                status_code=400,
                detail="Invalid query parameters: `q` is missing",
            )

    def normalize_query(self, query: str) -> str:
        """Remove trailing spaces from the query string and support both $(stock) and $ (stock)"""
        return query.strip().replace("$", "STOCK ").replace("  ", " ")

    async def query(self, srequest: SuggestionRequest) -> list[BaseSuggestion]:
        """Provide finance suggestions."""
        try:
            if srequest.source == "newtab":
                return await self._query_widget(srequest)

            # Get the list of tickers (0 to 3) for the query string.
            return await self._quote(get_tickers_for_query(srequest.query), tags={})
        except Exception as e:
            logger.warning(f"Exception occurred for Polygon provider: {e}")
            return []

    async def _query_widget(self, srequest: SuggestionRequest) -> list[BaseSuggestion]:
        """Serve the New Tab stocks widget.

        The widget sends three request shapes: an empty query for the default
        ETF set, a single ticker symbol for a quote, and free text with
        `request_type=ticker_search` for its search pick-list. Quote lookups
        bypass the curated mappings entirely; the widget obtains symbols from
        ticker search, stores them client-side, and asks for quotes one symbol
        per request, which keeps every upstream lookup independent.
        """
        if srequest.request_type == TICKER_SEARCH_REQUEST_TYPE:
            return await self._search_tickers(srequest)

        tickers = (
            get_tickers_for_newtab_query(srequest.query)
            if srequest.query
            else STOCKS_WIDGET_DEFAULT_ETFS
        )
        return await self._quote(tickers, tags={"source": "newtab"})

    async def _quote(
        self, tickers: list[str] | None, tags: dict[str, str]
    ) -> list[BaseSuggestion]:
        """Build one suggestion carrying a summary per ticker the backend could resolve."""
        if not tickers:
            return []

        with self.metrics_client.timeit("polygon.provider.query.latency", tags=tags):
            snapshots = await self.backend.get_snapshots(tickers)
            summaries: list[TickerSummary] = [
                self.backend.get_ticker_summary(
                    snapshot, self.get_image_url_for_ticker(snapshot.ticker)
                )
                for snapshot in snapshots
            ]

        return [self.build_suggestion(PolygonDetails(values=summaries))]

    async def _search_tickers(self, srequest: SuggestionRequest) -> list[BaseSuggestion]:
        """Serve a widget ticker search: candidate matches for free text.

        Unlike weather location completion, digit-bearing queries are not
        filtered as soft PII: names like "3M" are legitimate finance searches,
        and forwarding widget search input upstream is the approved design.
        """
        if not srequest.query:
            return []

        with self.metrics_client.timeit(
            "polygon.provider.search.latency", tags={"source": "newtab"}
        ):
            matches = await self.backend.search_tickers(srequest.query)

        if not matches:
            return []

        return [self.build_suggestion(PolygonDetails(values=[], matches=matches))]

    def build_suggestion(self, details: PolygonDetails) -> BaseSuggestion:
        """Wrap polygon details in the generic suggestion envelope."""
        return BaseSuggestion(
            title="Finance Suggestion",
            url=HttpUrl(self.url),
            provider=self.name,
            is_sponsored=False,
            score=self.score,
            custom_details=CustomDetails(polygon=details),
        )

    def get_image_url_for_ticker(self, ticker: str) -> HttpUrl | None:
        """Return the GCS url from the manifest for a given ticker symbol"""
        return self.manifest_data.tickers.get(ticker.upper()) if self.manifest_data else None

    async def shutdown(self) -> None:
        """Shut down the provider."""
        await self.backend.shutdown()
