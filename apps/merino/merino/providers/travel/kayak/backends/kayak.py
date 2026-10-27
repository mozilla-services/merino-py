"""Kayak backend for fetching travel listings from the Kayak affiliate API."""

import logging
from typing import Any

import aiodogstatsd
from httpx import AsyncClient, HTTPError, Response

from merino.providers.travel.kayak.backends.protocol import TravelListing, TravelVertical

logger = logging.getLogger(__name__)

DEFAULT_LANGUAGE = "en"
DEFAULT_MARKET = "us"

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
        self, query: str, locale: str, vertical: TravelVertical
    ) -> list[TravelListing]:
        """Fetch travel listings from Kayak's autocomplete API for the given vertical."""
        language, market = self._parse_locale(locale)
        url = f"{self.url_base}{self.url_autocomplete_path}".format(
            language=language, market=market, vertical=vertical
        )
        params = {"apiKey": self.api_key, "searchTerm": query}

        try:
            with self.metrics_client.timeit("kayak.request.autocomplete.get"):
                response: Response = await self.http_client.get(url, params=params)

            response.raise_for_status()
            results = response.json()["results"]

            # Flight results are only useful if they can be searched for by IATA code.
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
        """Map a Kayak flights autocomplete result to a travel listing."""
        return TravelListing(
            name=item["name"],
            full_name=item["fullName"],
            type=item["primaryPlaceType"],
            iata_code=item.get("iataCode"),
            place_id=item["placeId"],
            country=item.get("countryName"),
        )

    @staticmethod
    def _parse_locale(locale: str) -> tuple[str, str]:
        """Split a locale such as `en-US` into a lowercase (language, market) pair.

        Falls back to the default language and market if the locale cannot be parsed.
        """
        language, _, market = locale.lower().partition("-")
        if language.isalpha() and market.isalpha():
            return language, market

        return DEFAULT_LANGUAGE, DEFAULT_MARKET

    async def shutdown(self) -> None:
        """Close the HTTP client."""
        await self.http_client.aclose()
