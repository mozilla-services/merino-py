"""Kayak backend skeleton."""

from merino.providers.travel.kayak.backends.protocol import TravelListing, TravelVertical


class KayakBackend:
    """Backend that fetches travel listings from the Kayak API."""

    api_key: str
    url_base: str

    def __init__(self, api_key: str, url_base: str) -> None:
        self.api_key = api_key
        self.url_base = url_base

    async def get_listings(
        self, query: str, locale: str, vertical: TravelVertical
    ) -> list[TravelListing]:
        """Fetch travel listings from Kayak."""
        # TODO: integrate with the Kayak API.
        return []
