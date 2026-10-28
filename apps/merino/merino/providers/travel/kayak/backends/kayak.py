"""Kayak backend for fetching travel listings from the Kayak affiliate API."""

import logging
from typing import Any

import aiodogstatsd
from httpx import AsyncClient, HTTPError, Response

from merino.providers.travel.kayak.backends.protocol import TravelListing, TravelVertical

logger = logging.getLogger(__name__)

DEFAULT_LANGUAGE = "en"

# Kayak returns at most this many autocomplete results.
MAX_RESULTS = 6


class KayakBackend:
    """Backend that fetches travel listings from the Kayak API."""

    api_key: str
    http_client: AsyncClient
    url_base: str
    url_autocomplete_path: str
    metrics_client: aiodogstatsd.Client

    def __init__(
        self,
        api_key: str,
        http_client: AsyncClient,
        url_base: str,
        url_autocomplete_path: str,
        metrics_client: aiodogstatsd.Client,
    ) -> None:
        self.api_key = api_key
        self.http_client = http_client
        self.url_base = url_base
        self.url_autocomplete_path = url_autocomplete_path
        self.metrics_client = metrics_client

    async def get_listings(
        self, query: str, language: str, market: str, vertical: TravelVertical
    ) -> list[TravelListing]:
        """Fetch travel listings from Kayak's autocomplete API for the given vertical."""
        url = f"{self.url_base}{self.url_autocomplete_path}".format(
            language=self._parse_language(language), market=market.lower(), vertical=vertical
        )
        params = {"apiKey": self.api_key, "searchTerm": query}

        try:
            with self.metrics_client.timeit("kayak.request.autocomplete.get"):
                response: Response = await self.http_client.get(url, params=params)

            response.raise_for_status()
            results = response.json()["results"]

            # Filter out flight results that are missing IATA code
            if vertical == "flights":
                results = [item for item in results if item.get("iataCode")]

            listings = [self._to_listing(item) for item in results[:MAX_RESULTS]]
        except HTTPError as ex:
            logger.warning(
                "Kayak autocomplete request failed",
                extra={"vertical": vertical, "error": ex.__class__.__name__},
            )
            self.metrics_client.increment("kayak.request.autocomplete.failed")
            return []
        except (AttributeError, KeyError, TypeError, ValueError) as ex:
            logger.warning(
                "Kayak autocomplete response has incorrect shape",
                extra={"vertical": vertical, "error": type(ex).__name__},
            )
            self.metrics_client.increment("kayak.response.invalid")
            return []

        self.metrics_client.increment("kayak.request.autocomplete.success")
        return listings

    @staticmethod
    def _to_listing(item: dict[str, Any]) -> TravelListing:
        """Map a Kayak autocomplete result of any vertical to a travel listing."""
        return TravelListing(
            # Cars results have no `name`, so fall back to the full name.
            name=item.get("name") or item["fullName"],
            full_name=item["fullName"],
            type=item["primaryPlaceType"],
            iata_code=item.get("iataCode"),
            place_id=item["placeId"],
            city_id=item.get("cityId"),
            country=item.get("countryName"),
            hotel_id=item.get("hotelId"),
            entity_key=item.get("entityKey"),
        )

    @staticmethod
    def _parse_language(language: str) -> str:
        """Extract the lowercase primary language subtag from a language tag such as `en-US`.

        Falls back to the default language if the tag cannot be parsed.
        """
        primary, _, _ = language.lower().partition("-")
        return primary if primary.isalpha() else DEFAULT_LANGUAGE

    async def shutdown(self) -> None:
        """Close the HTTP client."""
        await self.http_client.aclose()
