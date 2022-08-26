from typing import Any

from merino.providers.base import BaseProvider


class WikiFruitProvider(BaseProvider):
    """
    A test provider for Wikipedia. Shouldn't be used in production.
    """

    async def initialize(self) -> None:
        pass

    async def query(self, query: str) -> list[dict[str, Any]]:
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

    def enabled_by_default(self) -> bool:
        return True
