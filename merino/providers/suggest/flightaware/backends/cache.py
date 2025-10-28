"""Provides a Redis-backed caching layer for FlightAware flight summaries, access tracking, and cleanup logic."""

import json
import logging
import time
import datetime
from typing import Any

from merino.cache.protocol import CacheAdapter
from merino.providers.suggest.flightaware.backends.protocol import FlightSummary
from merino.exceptions import CacheAdapterError

logger = logging.getLogger(__name__)

CACHE_KEY = "flight_status:{ident}"
LAST_ACCESS_ZSET = "flight_last_access"


class FlightCache:
    """Redis-backed cache for FlightAware flight summaries and metadata."""

    redis: CacheAdapter

    def __init__(self, redis_adapter: CacheAdapter):
        self.redis = redis_adapter

    async def get_flight(self, flight_num: str) -> dict[str, Any] | None:
        """Retrieve cached flight summaries and metadata."""
        key = CACHE_KEY.format(ident=flight_num)

        try:
            data = await self.redis.get(key)
            if not data:
                return None

            return json.loads(data.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None
        except CacheAdapterError as e:
            logger.warning(f"Error while getting flight summaries for {flight_num} : {e}")
            return None

    async def set_flight(
        self, flight_num: str, summaries: list[FlightSummary], ttl_seconds: int
    ) -> None:
        """Store flight summaries and metadata in redis."""
        key = CACHE_KEY.format(ident=flight_num)

        payload = {
            "fetched_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "summaries": [s.model_dump(mode="json") for s in summaries],
        }

        try:
            await self.redis.set(
                key,
                json.dumps(payload).encode("utf-8"),
                ttl=datetime.timedelta(seconds=ttl_seconds),
            )
        except CacheAdapterError as e:
            logger.warning(f"Error while setting flight summaries for {flight_num}: {e}")

    async def mark_accessed(self, flight_num: str) -> None:
        """Add recently accessed flight number to zset"""
        key = CACHE_KEY.format(ident=flight_num)
        try:
            await self.redis.zadd(LAST_ACCESS_ZSET, {key: time.time()})
        except CacheAdapterError as e:
            logger.warning(f"Error while marking flight number assessed for {flight_num} : {e}")
            return None

    async def prune_old_access_records(self, older_than_sec: int = 86400) -> int:
        """Remove old flight access records from the `flight_last_access` sorted set.

        Args:
            older_than_sec: Entries last accessed more than this many seconds ago
                will be removed (default 24 hours).

        Returns:
            The number of records removed.
        """
        try:
            now = time.time()
            cutoff = now - older_than_sec

            removed = await self.redis.zremrangebyscore(
                LAST_ACCESS_ZSET,
                min=0,
                max=cutoff,
            )

            if removed > 0:
                logger.debug(f"Pruned {removed} old records from {LAST_ACCESS_ZSET}")
            return removed

        except CacheAdapterError as e:
            logger.warning(f"Failed to prune old flight access records: {e}")
            return 0
