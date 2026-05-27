"""SportsData live query system"""

import asyncio
import hashlib
import json
import logging
import os
from collections.abc import Awaitable
from datetime import datetime, timedelta
from typing import Any

from httpx import AsyncClient, HTTPError, HTTPStatusError
from tenacity import (
    AsyncRetrying,
    RetryCallState,
    retry_if_exception,
    stop_after_attempt,
    wait_random_exponential,
)

from merino.configs import settings
from merino.providers.suggest.sports import LOGGING_TAG
from merino.providers.suggest.sports.backends.sportsdata.common.error import SportsDataError
from merino.utils.metrics import get_metrics_client

SPORTSDATA_DEFAULT_MAX_TRIES = 5
SPORTSDATA_DEFAULT_RETRY_FACTOR_SECONDS = 0.5
SPORTSDATA_RETRYABLE_STATUS_CODES = {408, 425, 429}
SPORTSDATA_STALE_FALLBACK_METRIC = "sports.fetch.stale_fallback"


def _sportsdata_retry_max_tries() -> int:
    """Return the configured number of SportsData fetch attempts."""
    return int(
        settings.providers.sports.sportsdata.get("retry_max_tries", SPORTSDATA_DEFAULT_MAX_TRIES)
    )


def _sportsdata_retry_factor_seconds() -> float:
    """Return the configured initial SportsData exponential backoff delay."""
    return float(
        settings.providers.sports.sportsdata.get(
            "retry_factor_sec", SPORTSDATA_DEFAULT_RETRY_FACTOR_SECONDS
        )
    )


def _sportsdata_status_suffix(error: HTTPError) -> str:
    """Return a concise HTTP status fragment for provider fetch logs/errors."""
    if isinstance(error, HTTPStatusError):
        return f" with status {error.response.status_code}"
    return ""


def _is_retryable_sportsdata_error(error: HTTPError) -> bool:
    """Return whether a SportsData fetch error is likely transient."""
    if not isinstance(error, HTTPStatusError):
        return True
    status_code = error.response.status_code
    return status_code in SPORTSDATA_RETRYABLE_STATUS_CODES or status_code >= 500


def _should_retry_sportsdata_error(error: BaseException) -> bool:
    """Return whether a SportsData fetch error should be retried."""
    return isinstance(error, HTTPError) and _is_retryable_sportsdata_error(error)


def _retry_detail_url(args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
    """Return the URL from retry callback details."""
    if url := kwargs.get("url"):
        return str(url)
    if len(args) >= 2:
        return str(args[1])
    return "unknown URL"


def _log_sportsdata_retry(retry_state: RetryCallState) -> None:
    """Log a SportsData request retry attempt."""
    exception = retry_state.outcome.exception() if retry_state.outcome else None
    status_suffix = (
        _sportsdata_status_suffix(exception) if isinstance(exception, HTTPError) else ""
    )
    url = _retry_detail_url(retry_state.args, retry_state.kwargs)
    wait = retry_state.next_action.sleep if retry_state.next_action else 0
    next_attempt = retry_state.attempt_number + 1
    max_tries = _sportsdata_retry_max_tries()
    logger = logging.getLogger(__name__)
    logger.warning(
        f"{LOGGING_TAG} Provider fetch failed{status_suffix}; "
        f"retrying {url} attempt {next_attempt}/{max_tries} "
        f"in {wait:.2f}s"
    )


def _record_stale_fallback(error: HTTPError) -> None:
    """Record that a stale SportsData cache entry was used after a fetch failure."""
    status = str(error.response.status_code) if isinstance(error, HTTPStatusError) else "unknown"
    get_metrics_client().increment(SPORTSDATA_STALE_FALLBACK_METRIC, tags={"status": status})


def _sportsdata_retry_sleep(seconds: float) -> Awaitable[None]:
    """Sleep between SportsData retry attempts."""
    return asyncio.sleep(seconds)


async def _fetch_provider_data_once(
    client: AsyncClient,
    url: str,
    request_args: dict[str, Any],
) -> Any:
    """Fetch and parse one SportsData response."""
    response = await client.get(url, **request_args)
    response.raise_for_status()
    return response.json()


async def _fetch_provider_data(
    client: AsyncClient,
    url: str,
    request_args: dict[str, Any],
) -> Any:
    """Fetch and parse one SportsData response with retryable transient errors."""
    retryer = AsyncRetrying(
        retry=retry_if_exception(_should_retry_sportsdata_error),
        wait=wait_random_exponential(multiplier=_sportsdata_retry_factor_seconds()),
        stop=stop_after_attempt(_sportsdata_retry_max_tries()),
        before_sleep=_log_sportsdata_retry,
        sleep=_sportsdata_retry_sleep,
        reraise=True,
    )
    return await retryer(_fetch_provider_data_once, client, url, request_args)


# TODO: convert this to use `sport.cache`; obsolete the `cache_dir` arg
async def get_data(
    client: AsyncClient,
    url: str,
    ttl: timedelta | None = None,
    cache_dir: str | None = None,
    args: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> Any:
    """Fetch data from the provider.

    Fresh cache entries are returned until `ttl` expires. When the provider fetch fails after
    retrying, an expired cache entry may be returned as a stale fallback.
    """
    logger = logging.getLogger(__name__)
    cache_file = None
    # TODO: Convert to using a GCS bucket?
    if cache_dir:
        # painfully stupid cacher.
        # does not have to be super secure.
        hasher = hashlib.new("sha1", usedforsecurity=False)
        hasher.update(url.encode())
        hash = hasher.hexdigest()
        cache_file = os.path.join(cache_dir, f"{hash}.json")
        if os.path.exists(cache_file):
            try:
                if ttl:
                    if os.path.getctime(cache_file) > (datetime.now() - ttl).timestamp():
                        logger.debug(f"{LOGGING_TAG}💾 Reading cache for {url}")
                        with open(cache_file, "r") as cache:
                            return json.load(cache)
                else:
                    logger.debug(f"{LOGGING_TAG}💾 Reading perma-cache for {url}")
                    with open(cache_file, "r") as cache:
                        return json.load(cache)
            except PermissionError:
                logger.warning(f"{LOGGING_TAG} Unable to read cache {cache_file}")
                pass
            except ValueError:
                # possible read on a closed file.
                pass
    logger.debug(f"{LOGGING_TAG} fetching data from {url}")
    request_args: dict[str, Any] = {"params": args}
    if headers:
        request_args["headers"] = headers
    try:
        response = await _fetch_provider_data(
            client=client,
            url=url,
            request_args=request_args,
        )
    except HTTPError as ex:
        if cache_file and os.path.exists(cache_file):
            try:
                logger.warning(
                    f"{LOGGING_TAG} Provider fetch failed; reading stale cache for {url}"
                )
                _record_stale_fallback(ex)
                with open(cache_file, "r") as cache:
                    return json.load(cache)
            except PermissionError:
                logger.warning(f"{LOGGING_TAG} Unable to read stale cache {cache_file}")
            except ValueError:
                logger.warning(f"{LOGGING_TAG} Unable to deserialize stale cache {cache_file}")
        raise SportsDataError(
            f"Could not fetch data from provider for {url}{_sportsdata_status_suffix(ex)}"
        ) from None
    if cache_file:
        logger.debug(f"{LOGGING_TAG}💾 Writing cache for {url}")
        try:
            with open(cache_file, "w") as cache:
                json.dump(response, cache)
        except PermissionError:
            logger.warning(f"{LOGGING_TAG} Unable to write cache {cache_file}")
            pass
        except TypeError:
            # Could not serialize the response, possibly due to it being a mock.
            logger.warning(f"{LOGGING_TAG} Unable to serialize response for {url}")
            pass
    return response
