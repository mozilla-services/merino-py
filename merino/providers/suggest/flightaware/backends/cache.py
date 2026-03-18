"""Provides a caching layer for FlightAware flight summaries."""

import json
import logging
import datetime

from pydantic import BaseModel, ValidationError

from merino.cache.protocol import CacheAdapter
from merino.providers.suggest.flightaware.backends.errors import (
    FlightawareError,
    FlightawareErrorMessages,
)
from merino.providers.suggest.flightaware.backends.protocol import FlightSummary
from merino.exceptions import CacheAdapterError

logger = logging.getLogger(__name__)

CACHE_KEY = "flight_status:{ident}"


class CachedFlightData(BaseModel):
    """Schema for stored flight data in Redis."""

    summaries: list[FlightSummary]


class FlightCache:
    """Redis-backed cache for FlightAware flight summaries and metadata."""

    redis: CacheAdapter

    def __init__(self, redis_adapter: CacheAdapter):
        self.redis = redis_adapter

    async def get_flight(self, flight_num: str) -> CachedFlightData | None:
        """Retrieve cached flight summaries and metadata."""
        key = CACHE_KEY.format(ident=flight_num)

        try:
            data = await self.redis.get(key)
            if not data:
                return None

            data_json = json.loads(data.decode("utf-8"))
            return CachedFlightData.model_validate(data_json)
        except (
            json.JSONDecodeError,
            UnicodeDecodeError,
            ValueError,
            ValidationError,
        ) as e:
            raise FlightawareError(
                FlightawareErrorMessages.CACHE_DATA_PARSING_ERROR,
                flight_num=flight_num,
            ) from e
        except CacheAdapterError as e:
            raise FlightawareError(
                FlightawareErrorMessages.CACHE_READ_ERROR,
                flight_num=flight_num,
            ) from e

    async def set_flight(
        self, flight_num: str, summaries: list[FlightSummary], ttl_seconds: int
    ) -> None:
        """Store flight summaries and metadata in redis."""
        key = CACHE_KEY.format(ident=flight_num)

        try:
            payload = {
                "summaries": [s.model_dump(mode="json") for s in summaries],
            }
            await self.redis.set(
                key,
                json.dumps(payload).encode("utf-8"),
                ttl=datetime.timedelta(seconds=ttl_seconds),
            )
        except (TypeError, ValueError, UnicodeEncodeError) as e:
            raise FlightawareError(
                FlightawareErrorMessages.CACHE_DATA_PARSING_ERROR,
                flight_num=flight_num,
            ) from e

        except CacheAdapterError as e:
            raise FlightawareError(
                FlightawareErrorMessages.CACHE_WRITE_ERROR,
                flight_num=flight_num,
            ) from e
