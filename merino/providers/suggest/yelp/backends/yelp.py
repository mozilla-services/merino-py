"""A wrapper for Yelp API interactions."""

import logging
from typing import Any

from httpx import AsyncClient, Response, HTTPStatusError

from merino.providers.suggest.yelp.backends.protocol import YelpBackendProtocol

LIMIT_DEFAULT = 1
logger = logging.getLogger(__name__)


class YelpBackend(YelpBackendProtocol):
    """Backend that connects to the Yelp API."""

    api_key: str
    http_client: AsyncClient
    url_business_search: str

    def __init__(
        self,
        api_key: str,
        http_client: AsyncClient,
        url_business_search: str,
    ) -> None:
        """Initialize the Yelp backend."""
        self.api_key = api_key
        self.http_client = http_client
        self.url_business_search = url_business_search

    async def get_businesses(self, search_term: str, location: str) -> dict | None:
        """Get businesses from Yelp calling its api."""
        headers = {"Authorization": f"Bearer {self.api_key}"}
        params = {"term": search_term, "location": location, "limit": LIMIT_DEFAULT}
        url = self.url_business_search.format(**params)
        try:
            response: Response = await self.http_client.get(url, headers=headers)
            response.raise_for_status()
            return self.process_response(response.json())
        except HTTPStatusError as ex:
            logger.warning(
                f"Yelp request error: Failed to get businesses for {search_term}/{location}: {ex.response.status_code} {ex.response.reason_phrase}"
            )
        return None

    @staticmethod
    def process_response(response: Any) -> dict | None:
        """Process response from Yelp."""
        try:
            business = response["businesses"][0]
            name = business["name"]
            url = business["url"]
            address = business["location"]["address1"]
            business_hours = business["business_hours"]
            # extract potentially null fields
            price = business.get("price")
            rating = business.get("rating")
            review_count = business.get("review_count")

            return {
                "name": name,
                "url": url,
                "address": address,
                "rating": rating,
                "price": price,
                "review_count": review_count,
                "business_hours": business_hours,
            }

        except (KeyError, IndexError):
            logger.warning(f"Yelp business response json has incorrect shape: {response}")
            return None

    async def shutdown(self) -> None:
        """Shutdown any persistent connections. Currently a no-op."""
        pass
