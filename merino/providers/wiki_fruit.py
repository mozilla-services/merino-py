"""A Suggestion provider that provides toy responses, meant for development and testing purposes"""
from typing import Any

from merino.providers.base import BaseProvider


class WikiFruitProvider(BaseProvider):
    """A test provider for Wikipedia.

    Shouldn't be used in production.
    """

    def __init__(self, name: str, enabled_by_default: bool):
        """Init for WikiFruitProvider."""
        self._enabled_by_default = enabled_by_default
        self._name = name

    async def initialize(self) -> None:
        """Initialize wiki fruit"""
        pass

    async def query(self, query: str) -> list[dict[str, Any]]:
        """Provide wiki_fruit suggestsion based on query."""
        if query not in ["apple", "banana", "cherry"]:
            return []

        return [
            {
                "block_id": 1,
                "full_keyword": query,
                "title": f"Wikipedia - {query.capitalize()}",
                "url": f"https://en.wikipedia.org/wiki/{query.capitalize()}",
                "impression_url": "https://127.0.0.1/",
                "click_url": "https://127.0.0.1/",
                "provider": "test_wiki_fruit",
                "advertiser": "test_advertiser",
                "is_sponsored": False,
                "icon": "https://en.wikipedia.org/favicon.ico",
                "score": 0,
            }
        ]
