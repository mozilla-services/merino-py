"""Travel provider module that contains logic and methods to provide travel listings for different verticals."""

from typing import Any

import aiodogstatsd

from merino.providers.travel.kayak.backends.protocol import (
    TravelBackend,
    TravelListing,
    TravelVertical,
)

# Verticals currently backed by the Kayak API. Others return no listings.
SUPPORTED_VERTICALS: frozenset[TravelVertical] = frozenset({"flights"})


class Provider:
    """Provider for travel listings."""

    backend: TravelBackend
    metrics_client: aiodogstatsd.Client

    def __init__(
        self,
        backend: TravelBackend,
        metrics_client: aiodogstatsd.Client,
        name: str,
        enabled: bool = False,
        **kwargs: Any,
    ) -> None:
        self.backend = backend
        self.metrics_client = metrics_client
        self.name = name
        self._enabled = enabled

    async def get_listings(
        self, query: str, locale: str, vertical: TravelVertical
    ) -> list[TravelListing]:
        """Return travel listings for the given query, locale and vertical."""
        if not self._enabled or vertical not in SUPPORTED_VERTICALS:
            return []

        return await self.backend.get_listings(query, locale, vertical)

    async def shutdown(self) -> None:
        """Shut down the provider's backend."""
        await self.backend.shutdown()
