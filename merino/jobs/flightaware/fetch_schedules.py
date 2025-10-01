"""Fetches and stores flight schedules from flightaware."""

import datetime
import logging
from typing import Any
import httpx
import json

from merino.cache.none import NoCacheAdapter
from merino.cache.redis import RedisAdapter, create_redis_clients
from merino.configs import settings
from merino.exceptions import CacheAdapterError
from merino.utils.gcs.gcs_uploader import GcsUploader
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)


logger = logging.getLogger(__name__)

setting = settings.providers.flightaware
cache = (
    RedisAdapter(
        *create_redis_clients(
            settings.redis.server,
            settings.redis.replica,
            settings.redis.max_connections,
            settings.redis.socket_connect_timeout_sec,
            settings.redis.socket_timeout_sec,
        )
    )
    if setting.cache == "redis"
    else NoCacheAdapter()
)


FLIGHTAWARE_API_KEY = settings.flightaware.api_key
STORAGE = settings.flightaware.storage
SCHEDULES_URL = settings.flightaware.schedules_url_path

CHUNK_SIZE = 100_000


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    retry=retry_if_exception_type(httpx.HTTPError),
    reraise=True,
)
def _get_with_retry(client: httpx.Client, url: str, headers: dict[str, str]) -> httpx.Response:
    """Perform a GET request with retries for HTTP errors"""
    resp = client.get(url, headers=headers, timeout=60)
    resp.raise_for_status()
    return resp


def fetch_schedules(client: httpx.Client) -> tuple[set[str], int]:
    """Fetch schedules for a 6-hour rolling window and accumulate flight numbers in Redis."""
    now = datetime.datetime.now(datetime.timezone.utc)
    start = now.isoformat(timespec="seconds").replace("+00:00", "Z")
    end = (now + datetime.timedelta(hours=6)).isoformat(timespec="seconds").replace("+00:00", "Z")

    url: str | None = SCHEDULES_URL.format(start=start, end=end)
    headers = {"x-apikey": FLIGHTAWARE_API_KEY}
    flight_number_set: set[str] = set()
    page = 1
    api_calls = 0

    while url is not None:
        try:
            assert url is not None  # helps Mypy narrow type
            resp = _get_with_retry(client, url, headers)
            api_calls += 1
            resp.raise_for_status()
            data = resp.json()

            scheduled_flights = data.get("scheduled", [])
            logger.info(f"Page {page}: {len(scheduled_flights)} flights")

            process_flight_numbers(flight_number_set, scheduled_flights)

            links = data.get("links") or {}
            url = links.get("next", None)

        except httpx.HTTPStatusError as ex:
            logger.error(
                f"Failed to fetch page {page}: {ex.response.status_code} {ex.response.reason_phrase}"
            )
            url = None

    return flight_number_set, api_calls


def process_flight_numbers(
    flight_number_set: set[str],
    scheduled_flights: list[dict[str, Any]],
) -> None:
    """Add unique flight numbers to a set"""
    for flight in scheduled_flights:
        flight_num = flight.get("ident_iata", None)
        if flight_num:
            flight_number_set.add(flight_num)
    logger.info(f"Unique flight numbers so far: {len(flight_number_set)}")


async def store_flight_numbers(flight_number_set: set[str]) -> None:
    """Accumulate flight numbers using the configured storage (Redis or GCS)"""
    if not flight_number_set:
        logger.info("No flight numbers to persist.")
        return

    if STORAGE == "redis":
        await store_flight_numbers_in_redis(flight_number_set)

    elif STORAGE == "gcs":
        await store_flight_numbers_in_gcs(flight_number_set)

    else:
        logger.warning(f"Unknown storage backend '{STORAGE}', skipping persist.")


async def store_flight_numbers_in_redis(flight_number_set: set[str]) -> None:
    """Insert flight numbers into Redis in chunks and log new additions."""
    try:
        numbers = list(flight_number_set)
        newly_added_total = 0
        for i in range(0, len(numbers), CHUNK_SIZE):
            chunk = numbers[i : i + CHUNK_SIZE]
            added = await cache.sadd("flights:valid", *chunk)
            newly_added_total += added

        total = await cache.scard("flights:valid")
        logger.info(f"Added {newly_added_total} new flight numbers; total now {total} in Redis")
    except CacheAdapterError as e:
        logger.error(f"Error storing flight numbers in Redis: {e}")


async def store_flight_numbers_in_gcs(flight_number_set: set[str]) -> None:
    """Add new unique flight numbers in GCS and log additions."""
    try:
        uploader = GcsUploader(
            settings.image_gcs.gcs_project,
            settings.image_gcs.gcs_bucket,
            settings.image_gcs.cdn_hostname,
        )

        existing_blob = uploader.get_most_recent_file(
            match="flight_numbers",
            sort_key=lambda b: b.updated,
        )

        existing_numbers: set[str] = set()
        if existing_blob:
            logger.info(f"Downloading existing blob {existing_blob.name} for deduplication")

            existing_numbers.update(json.loads(existing_blob.download_as_text()))

        combined = existing_numbers.union(flight_number_set)
        newly_added = combined - existing_numbers
        content = json.dumps(sorted(combined), indent=2)

        uploader.upload_content(
            content=content,
            destination_name="flight_numbers_latest.json",
            content_type="application/json",
            forced_upload=True,
        )
        logger.info(
            f"Uploaded {len(newly_added)} new flight numbers; total now {len(combined)} in GCS"
        )
    except Exception as e:
        logger.error(f"Error uploading flight numbers to GCS: {e}")
