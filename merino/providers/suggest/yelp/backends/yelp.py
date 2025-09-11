"""A wrapper for Yelp API interactions with Redis caching."""

import hashlib
import logging
from datetime import timedelta, datetime, time
from typing import Any, Optional
from zoneinfo import ZoneInfo

import aiodogstatsd
import orjson
from httpx import AsyncClient, Response, HTTPStatusError

from merino.cache.protocol import CacheAdapter
from merino.cache.redis import CacheAdapterError
from merino.providers.suggest.yelp.backends.keyword_mapping import CATEGORIES
from merino.middleware.geolocation import Location
from merino.providers.suggest.yelp.backends.protocol import YelpBackendProtocol

LIMIT_DEFAULT = 1
logger = logging.getLogger(__name__)

YELP_ICON_URL = "https://firefox-settings-attachments.cdn.mozilla.net/main-workspace/quicksuggest-other/6f44101f-8385-471e-b2dd-2b2ed6624637.svg"


class YelpBackend(YelpBackendProtocol):
    """Backend that connects to the Yelp API."""

    api_key: str
    http_client: AsyncClient
    url_business_search: str
    cache: Optional[CacheAdapter]
    cache_ttl_sec: int
    metrics_client: aiodogstatsd.Client

    def __init__(
        self,
        api_key: str,
        http_client: AsyncClient,
        url_business_search: str,
        cache_ttl_sec: int,  # 24 hours
        metrics_client: aiodogstatsd.Client,
        cache: Optional[CacheAdapter] = None,
    ) -> None:
        """Initialize the Yelp backend."""
        self.api_key = api_key
        self.http_client = http_client
        self.url_business_search = url_business_search
        self.cache_ttl_sec = cache_ttl_sec
        self.cache = cache
        self.metrics_client = metrics_client

    def generate_cache_key(self, search_term: str, location: str) -> str:
        """Generate cache key using consistent hashing approach."""
        # Create a consistent hash of the search parameters
        hasher = hashlib.blake2s()
        hasher.update(search_term.lower().encode("utf-8"))
        hasher.update(location.lower().encode("utf-8"))
        params_hash = hasher.hexdigest()

        return f"{self.__class__.__name__}:v1:business_search:{params_hash}"

    async def get_from_cache(self, cache_key: str) -> Any:
        """Get data from Redis cache."""
        if not self.cache:
            return None

        try:
            cached_data = await self.cache.get(cache_key)
            if cached_data:
                self.metrics_client.increment("yelp.cache.hit")
                return orjson.loads(cached_data)
        except CacheAdapterError as e:
            logger.warning(f"Yelp cache get error for {cache_key}: {e}")
            self.metrics_client.increment("yelp.cache.error")
        except Exception as e:
            logger.warning(f"Yelp cache decode error for {cache_key}: {e}")
            self.metrics_client.increment("yelp.cache.decode_error")

        return None

    async def store_in_cache(self, cache_key: str, data: dict) -> None:
        """Store data in Redis cache with TTL."""
        if not self.cache:
            return

        try:
            cached_value = orjson.dumps(data)
            await self.cache.set(
                cache_key, cached_value, ttl=timedelta(seconds=self.cache_ttl_sec)
            )
            logger.debug(f"Yelp cached response: {cache_key}")
            self.metrics_client.increment("yelp.cache.set")
        except CacheAdapterError as e:
            logger.warning(f"Yelp cache set error for {cache_key}: {e}")
            self.metrics_client.increment("yelp.cache.set_error")
        except Exception as e:
            logger.error(f"Yelp cache store error for {cache_key}: {e}")
            self.metrics_client.increment("yelp.cache.store_error")

    async def get_business(self, search_term: str, geolocation: Location) -> dict | None:
        """Get businesses from Yelp calling its api."""
        city = geolocation.city
        timezone = geolocation.timezone
        if city and timezone and search_term in CATEGORIES:
            # Generate cache key
            cache_key = self.generate_cache_key(search_term, city)

            # Try cache first
            cached_result = await self.get_from_cache(cache_key)
            if cached_result is not None and self.is_open_now(
                cached_result["business_hours"][0]["open"], timezone
            ):
                return self.format_business_hours(cached_result, timezone)

            # Cache miss - fetch from API
            logger.debug(f"Yelp cache miss, calling API: {search_term}/{city}")
            self.metrics_client.increment("yelp.cache.miss")
            api_result = await self.fetch(search_term, city)

            # Store in cache if successful
            if api_result is not None:
                await self.store_in_cache(cache_key, api_result)
                return self.format_business_hours(api_result, timezone)
        return None

    async def fetch(self, search_term: str, location: str) -> dict | None:
        """Get businesses from Yelp API."""
        headers = {"Authorization": f"Bearer {self.api_key}"}
        url = self.url_business_search.format(
            term=search_term, location=location, limit=LIMIT_DEFAULT
        )
        try:
            with self.metrics_client.timeit("yelp.request.business_search.get"):
                response: Response = await self.http_client.get(url, headers=headers)

            response.raise_for_status()
            result = self.process_response(response.json())

            if result is not None:
                self.metrics_client.increment("yelp.request.business_search.success")
            else:
                self.metrics_client.increment("yelp.business.invalid_response")

            return result
        except HTTPStatusError as ex:
            logger.warning(
                f"Yelp request error: Failed to get businesses for {search_term}/{location}: {ex.response.status_code} {ex.response.reason_phrase}"
            )
            self.metrics_client.increment("yelp.request.business_search.failed")
        return None

    @staticmethod
    def process_response(response: Any) -> dict | None:
        """Process response from Yelp."""
        try:
            business = response["businesses"][0]
            name = business["name"]
            url = business["url"]
            address = business["location"]["address1"]
            city = business["location"]["city"]
            business_hours = business["business_hours"]
            # extract potentially null fields
            price = business.get("price")
            rating = business.get("rating")
            review_count = business.get("review_count")

            return {
                "name": name,
                "url": url,
                "city": city,
                "address": address,
                "rating": rating,
                "price": price,
                "review_count": review_count,
                "business_hours": business_hours,
                "image_url": YELP_ICON_URL,
            }

        except (KeyError, IndexError):
            logger.warning(f"Yelp business response json has incorrect shape: {response}")
            return None

    @staticmethod
    def is_open_now(business_hours: list[dict[str, Any]], timezone: str) -> bool:
        """Determine whether business is open based on current time.

        Args:
            business_hours: business hours from yelp.
                ex [{"start": "1100", "end": "1800"}...]
            timezone: local timezone string of the business
        """
        now = datetime.now(ZoneInfo(timezone))
        day = now.weekday()
        hour = now.hour
        minute = now.minute
        time_now = time(hour, minute)
        try:
            # parse time strings into time
            start_string = business_hours[day]["start"]
            start_time = time(int(start_string[:2]), int(start_string[2:]))
            end_string = business_hours[day]["end"]
            end_time = time(int(end_string[:2]), int(end_string[2:]))

            if start_time == time(0) and end_time == time(0):
                return True
            return start_time <= time_now <= end_time
        except (KeyError, IndexError):
            logger.warning(f"Yelp business hours has incorrect shape: {business_hours}")
            return False

    @staticmethod
    def format_business_hours(response: dict[str, Any], timezone: str) -> dict[str, Any] | None:
        """Format response to give only today's business hours."""
        now = datetime.now(ZoneInfo(timezone))
        weekday = now.weekday()
        try:
            business_hours = response["business_hours"][0]["open"]
            today_hours = business_hours[weekday]
            start = today_hours["start"]
            end = today_hours["end"]
            return {**response, "business_hours": {"start": start, "end": end}}
        except (KeyError, IndexError):
            logger.warning(f"Yelp business hours has incorrect shape: {response}")
            return None

    async def shutdown(self) -> None:
        """Shutdown any persistent connections. Currently a no-op."""
        await self.http_client.aclose()
        if self.cache:
            await self.cache.close()
