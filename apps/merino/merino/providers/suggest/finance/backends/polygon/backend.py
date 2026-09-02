"""A wrapper for Polygon API interactions."""

import asyncio
import itertools
import hashlib
import logging
import aiodogstatsd
from httpx import AsyncClient, HTTPError, HTTPStatusError, Response
import orjson
from pydantic import HttpUrl, ValidationError
from merino.configs import settings
from typing import Any, Tuple, Optional

from merino.providers.suggest.finance.backends.polygon.filemanager import (
    PolygonFilemanager,
)
from merino.providers.suggest.finance.backends.protocol import (
    FinanceManifest,
    GetManifestResultCode,
    TickerMatch,
    TickerSnapshot,
    TickerSummary,
)
from merino.cache.protocol import CacheAdapter
from merino.exceptions import CacheAdapterError
from merino.providers.suggest.finance.backends.polygon.errors import (
    PolygonError,
    PolygonErrorMessages,
)
from merino.providers.suggest.finance.backends.polygon.stock_ticker_company_mapping import (
    ALL_STOCK_TICKER_COMPANY_MAPPING,
)
from merino.providers.suggest.finance.backends.polygon.utils import (
    TICKER_SYMBOL_PATTERN,
    extract_snapshot_if_valid,
    extract_ticker_matches_from_search_response,
    build_ticker_summary,
    generate_cache_key_for_ticker,
    rank_ticker_matches,
)
from merino.utils.gcs.gcs_uploader import GcsUploader
from merino.utils.gcs.models import Image

# Export all the classes from this module
__all__ = [
    "PolygonBackend",
]

logger = logging.getLogger(__name__)

GCS_BLOB_NAME = "polygon_latest.json"

# Upper bound on matches returned to the stocks widget's search pick-list.
TICKER_SEARCH_LIMIT: int = settings.providers.polygon.search_result_limit

# The search API orders matches by ticker, not relevance, so the real hit can
# sit far down the alphabet. Fetch a wider window for ranking to work with.
TICKER_SEARCH_UPSTREAM_LIMIT: int = settings.providers.polygon.search_upstream_limit

# Below this many characters the substring search returns an alphabetical slice
# of the whole market, so only the exact symbol lookup runs.
TICKER_SEARCH_MIN_QUERY_LENGTH: int = settings.providers.polygon.search_min_query_length

# The Lua script to write ticker snapshots and their TTLs for a list of keys.
#
# Note:
#   - TTL is the last value in the ARGV list and is the same for all keys.
LUA_SCRIPT_CACHE_BULK_WRITE_TICKERS: str = """
local ttl = ARGV[#ARGV]

for i = 1, #KEYS do
  redis.call('SET', KEYS[i], ARGV[i], 'EX', ttl)
end

return #KEYS
"""
SCRIPT_ID_BULK_WRITE_TICKERS: str = "bulk_write_tickers"


# The Lua script to fetch cached ticker snapshots and their TTLs for a list of keys.
#
# Note:
#   - The script expects each key to contain a JSON-serialized ticker snapshot string.
#   - For every existing key, it returns the snapshot value followed by its TTL (in seconds).
#   - Keys that are missing or expired are skipped and not included in the result.
LUA_SCRIPT_CACHE_BULK_FETCH_TICKERS: str = """
local result = {}
for _, k in ipairs(KEYS) do
  local snapshot = redis.call('GET', k)
  if snapshot then
    local ttl = redis.call('TTL', k)
    if ttl > 0 then
      table.insert(result, snapshot)
      table.insert(result, ttl)
    end
  end
end
return result
"""
SCRIPT_ID_BULK_FETCH_TICKERS: str = "bulk_fetch_tickers"


class PolygonBackend:
    """Backend that connects to the Polygon API."""

    api_key: str
    cache: CacheAdapter
    ticker_ttl_sec: int
    metrics_client: aiodogstatsd.Client
    http_client: AsyncClient
    metrics_sample_rate: float
    gcs_uploader: GcsUploader
    url_param_api_key: str
    url_single_ticker_snapshot: str
    url_single_ticker_overview: str
    url_reference_tickers: str
    filemanager: PolygonFilemanager

    def __init__(
        self,
        api_key: str,
        cache: CacheAdapter,
        ticker_ttl_sec: int,
        url_param_api_key: str,
        url_single_ticker_snapshot: str,
        url_single_ticker_overview: str,
        url_reference_tickers: str,
        metrics_client: aiodogstatsd.Client,
        http_client: AsyncClient,
        gcs_uploader: GcsUploader,
        metrics_sample_rate: float,
    ) -> None:
        """Initialize the Polygon backend."""
        self.api_key = api_key
        self.cache = cache
        self.ticker_ttl_sec = ticker_ttl_sec
        self.metrics_client = metrics_client
        self.http_client = http_client
        self.metrics_sample_rate = metrics_sample_rate
        self.url_param_api_key = url_param_api_key
        self.gcs_uploader = gcs_uploader
        self.url_single_ticker_snapshot = url_single_ticker_snapshot
        self.url_single_ticker_overview = url_single_ticker_overview
        self.url_reference_tickers = url_reference_tickers
        self.filemanager = PolygonFilemanager(
            gcs_bucket_path=settings.image_gcs.gcs_bucket,
            blob_name=GCS_BLOB_NAME,
        )
        # This registration is lazy (i.e. no interaction with Redis) and infallible.
        # Read script.
        self.cache.register_script(
            SCRIPT_ID_BULK_FETCH_TICKERS, LUA_SCRIPT_CACHE_BULK_FETCH_TICKERS
        )
        # Write script.
        self.cache.register_script(
            SCRIPT_ID_BULK_WRITE_TICKERS, LUA_SCRIPT_CACHE_BULK_WRITE_TICKERS
        )
        self.cache_control = settings.providers.polygon.image_cache_control

    async def get_snapshots(self, tickers: list[str]) -> list[TickerSnapshot]:
        """Get snapshots for the list of tickers.

        Raises:
            PolygonError: When an upstream snapshot request fails.
        """
        # check the cache first.
        cached = await self.get_snapshots_from_cache(tickers)
        # each tuple has the shape of `(snapshot, ttl)` and ignore the none tuples for now.
        cached_snapshots = [tupl[0] for tupl in cached if tupl is not None]

        # Determine which tickers were cached and which were not.
        cached_ticker_set = {s.ticker for s in cached_snapshots}
        missed_tickers = [t for t in tickers if t not in cached_ticker_set]

        # Emit metrics based on cache coverage.
        if not missed_tickers:
            self.metrics_client.increment("polygon.snapshot.cache.hit")
        elif cached_snapshots:
            self.metrics_client.increment("polygon.snapshot.cache.partial_hit")
        else:
            self.metrics_client.increment("polygon.snapshot.cache.miss")

        # Fetch any missing tickers from the API, one request per ticker. The
        # approved use of the upstream API requires that a user's symbols are
        # requested independently and never combined into one request.
        fetched_snapshots: list[TickerSnapshot] = []
        for ticker in missed_tickers:
            if (
                snapshot := extract_snapshot_if_valid(await self.fetch_ticker_snapshot(ticker))
            ) is not None:
                fetched_snapshots.append(snapshot)
            else:
                self.metrics_client.increment("polygon.snapshot.invalid")

        # Cache only the newly fetched snapshots.
        await self.store_snapshots_in_cache(fetched_snapshots)

        # Merge cached and freshly fetched snapshots into a lookup by ticker symbol.
        all_snapshots = cached_snapshots + fetched_snapshots
        snapshot_by_ticker: dict[str, TickerSnapshot] = {s.ticker: s for s in all_snapshots}

        # Return results in the original requested order, skipping any tickers
        # that failed to load from both cache and API.
        return [snapshot_by_ticker[t] for t in tickers if t in snapshot_by_ticker]

    def get_ticker_summary(
        self, snapshot: TickerSnapshot, image_url: HttpUrl | None
    ) -> TickerSummary:
        """Get a ticker summary for an individual ticker snapshot.
        Simply calls the util function since that is not exposed to the provider.
        """
        return build_ticker_summary(snapshot, image_url)

    async def get_snapshots_from_cache(
        self, tickers: list[str]
    ) -> list[Optional[Tuple[TickerSnapshot, int]]]:
        """Return snapshots from the cache with their respective TTLs in a list of tuples format."""
        try:
            cache_keys = []
            for ticker in tickers:
                cache_keys.append(generate_cache_key_for_ticker(ticker))

            cached_data: list[bytes | None] = await self.cache.run_script(
                sid=SCRIPT_ID_BULK_FETCH_TICKERS,
                keys=cache_keys,
                args=[],
                readonly=True,
            )

            if cached_data:
                parsed_cached_data = self._parse_cached_data(cached_data)
                return parsed_cached_data
        except CacheAdapterError as exc:
            logger.error(f"Failed to fetch snapshots from Redis: {exc}")

            # TODO @Herraj -- Propagate the error for circuit breaking as PolygonError.
        return []

    async def search_tickers(self, query: str) -> list[TickerMatch]:
        """Search the reference tickers endpoint by symbol or company name.

        The search API matches substrings anywhere in the name and orders
        results by ticker, so the intended security can fall outside the
        response window entirely (searching "EA" returns names containing
        "ea"). For symbol-shaped queries an exact ticker lookup therefore runs
        concurrently and its hit is ranked first; the remaining matches are
        fetched with a wider window and re-ranked by relevance. Queries below
        the minimum length skip the substring search, which would only return
        an alphabetical slice of the market.

        Results are intentionally not cached: the query is free text typed by
        the user, mirroring how weather location completion talks to its API.

        Raises:
            PolygonError: When an upstream request fails.
        """
        query = query.strip()
        symbol = query.upper()

        try:
            async with asyncio.TaskGroup() as tg:
                search_task = (
                    tg.create_task(
                        self._fetch_reference_tickers(
                            {"search": query, "limit": str(TICKER_SEARCH_UPSTREAM_LIMIT)}
                        )
                    )
                    if len(query) >= TICKER_SEARCH_MIN_QUERY_LENGTH
                    else None
                )
                exact_task = (
                    tg.create_task(self._fetch_reference_tickers({"ticker": symbol}))
                    if TICKER_SYMBOL_PATTERN.match(symbol)
                    else None
                )
        except ExceptionGroup as e:
            # The task group wraps failures; surface one backend error so the
            # provider's circuit breaker can count it.
            raise PolygonError(PolygonErrorMessages.FAILED_TICKER_SEARCH, exceptions=e.exceptions)

        exact = exact_task.result() if exact_task is not None else []
        searched = search_task.result() if search_task is not None else []
        exact_tickers = {match.ticker for match in exact}
        ranked = [
            match
            for match in rank_ticker_matches(searched, query)
            if match.ticker not in exact_tickers
        ]

        return (exact + ranked)[:TICKER_SEARCH_LIMIT]

    async def _fetch_reference_tickers(self, params: dict[str, str]) -> list[TickerMatch]:
        """Make one reference tickers request and extract the matches."""
        request_params = {
            "market": "stocks",
            "active": "true",
            self.url_param_api_key: self.api_key,
            **params,
        }
        response = await self._get_json("search", self.url_reference_tickers, request_params)
        return extract_ticker_matches_from_search_response(response)

    async def fetch_ticker_snapshot(self, ticker: str) -> Any:
        """Fetch the snapshot for one ticker.

        Raises:
            PolygonError: When the upstream request fails.
        """
        params = {"ticker": ticker, self.url_param_api_key: self.api_key}
        return await self._get_json("snapshot", self.url_single_ticker_snapshot, params)

    async def _get_json(self, operation: str, url: str, params: dict[str, str]) -> Any:
        """Issue one upstream GET on the request path and return the decoded body.

        Emits `polygon.request.<operation>.get` counters and latency. Any HTTP
        failure, including timeouts, is logged once and re-raised as a
        `PolygonError` for the provider to handle.
        """
        self.metrics_client.increment(f"polygon.request.{operation}.get")
        try:
            with self.metrics_client.timeit(f"polygon.request.{operation}.get.latency"):
                response: Response = await self.http_client.get(url, params=params)
            response.raise_for_status()
        except HTTPError as ex:
            self.metrics_client.increment(f"polygon.request.{operation}.get.failed")
            detail = (
                f"{ex.response.status_code} {ex.response.reason_phrase}"
                if isinstance(ex, HTTPStatusError)
                else type(ex).__name__
            )
            logger.warning(f"Polygon {operation} request failed: {detail}")
            raise PolygonError(
                PolygonErrorMessages.HTTP_REQUEST_ERROR, operation=operation, detail=detail
            ) from ex

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
        uploaded_urls: dict[str, str] = {}

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
                        cache_control=self.cache_control,
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

    async def fetch_manifest_data(
        self,
    ) -> tuple[GetManifestResultCode, FinanceManifest | None]:
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
            url_map = await self.bulk_download_and_upload_ticker_images(
                list(ALL_STOCK_TICKER_COMPANY_MAPPING.keys())
            )

            manifest = self.build_finance_manifest(url_map)
            manifest_bytes = orjson.dumps(manifest.model_dump(mode="json"))

            blob = self.gcs_uploader.upload_content(
                content=manifest_bytes,
                destination_name=GCS_BLOB_NAME,
                content_type="application/json",
                forced_upload=True,
            )

            if blob is None:
                logger.error("polygon manifest upload failed.")
        except Exception as e:
            logger.error(f"Error building/uploading manifest: {e}")
            return None

    async def store_snapshots_in_cache(self, snapshots: list[TickerSnapshot]) -> None:
        """Store a list of ticker snapshots in the cache.

        Each snapshot is serialized to JSON and written under a generated cache key
        for its ticker symbol, with a configured TTL applied.
        """
        if len(snapshots) == 0:
            return

        cache_keys: list[str] = [
            generate_cache_key_for_ticker(snapshot.ticker) for snapshot in snapshots
        ]
        cache_values: list[bytes] = [
            orjson.dumps(snapshot.model_dump_json()) for snapshot in snapshots
        ]

        try:
            await self.cache.run_script(
                sid=SCRIPT_ID_BULK_WRITE_TICKERS,
                keys=cache_keys,
                args=[
                    *cache_values,
                    self.ticker_ttl_sec,  # the last value is the TTL used for all keys
                ],
            )
        except CacheAdapterError as exc:
            logger.error(f"Failed to write snapshots to Redis: {exc}")

    # TODO @herraj add unit tests for this
    def _parse_cached_data(
        self, cached_data: list[bytes | None]
    ) -> list[Optional[Tuple[TickerSnapshot, int]]]:
        """Parse Redis output of the form [snapshot_json, ttl, snapshot_json, ttl, ...].
        Each snapshot is JSON-decoded and validated into a `TickerSnapshot`,
        and each TTL is converted to an int.

        Returns:
            A list of (TickerSnapshot, int) tuples for valid entries.
            Invalid or None pairs are skipped.
        """
        # Valid cached_data length should be an even number (multiple of 2) length e.g
        # [snapshot_1, ttl_1, snapshot_2, ttl_2, ...]
        if (len(cached_data) % 2) != 0:
            return []

        result: list[Optional[Tuple[TickerSnapshot, int]]] = []

        # every even index is a snapshot and odd index is its TTL
        for snapshot, ttl in itertools.batched(cached_data, 2):
            try:
                if snapshot is None or ttl is None:
                    continue

                # Parse snapshot JSON (bytes -> dict) then validate
                valid_snapshot = TickerSnapshot.model_validate_json(orjson.loads(snapshot))

                # Convert TTL bytes to int
                ttl_int = int(ttl)

                result.append((valid_snapshot, ttl_int))

            except ValidationError as exc:
                logger.error(f"TickerSnapshot validation failed: {exc}")
            except Exception as exc:
                logger.exception(f"Unexpected error parsing cached pair: {exc}")

        return result

    async def shutdown(self) -> None:
        """Close http client and cache connections."""
        logger.info("Shutting down polygon backend")
        await self.cache.close()
        await self.http_client.aclose()
        logger.info("polygon backend successfully shut down")
