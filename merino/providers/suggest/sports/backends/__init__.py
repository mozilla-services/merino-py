"""SportsData live query system"""

import logging
import os
from datetime import datetime, timedelta, timezone
from httpx import AsyncClient

from typing import Any

from merino.providers.suggest.sports import DEFAULT_LOGGING_LEVEL


async def get_data(client: AsyncClient, url: str) -> Any:
    """Wrapper for commonly called remote data fetch"""
    response = await client.get(url)
    response.raise_for_status()
    return response.json()


class SportSuggestion(dict):
    """Return a well structured Suggestion for the UA to process"""

    # Required fields.
    provider: str
    rating: float

    def as_suggestion(self) -> dict[str, Any]:
        return dict(
            provider=self.provider,
            rating=self.rating,
            # Return the random values we've collected as the "custom details"
            custom_details=dict(zip(self.keys(), self.values())),
        )
