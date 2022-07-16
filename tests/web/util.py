from typing import Any

from merino.providers.base import BaseProvider, DefaultProvider


class SponsoredProvider(BaseProvider, DefaultProvider):
    """
    A test sponsored provider that only responds to query "sponsored".
    """

    def __init__(self) -> None:
        ...

    def enabled_by_default(self) -> bool:
        return True

    def hidden(self) -> bool:
        return False

    async def query(self, q: str) -> list[dict[str, Any]]:
        if q.lower() == "sponsored":
            return [
                {
                    "block_id": 0,
                    "full_keyword": "sponsored",
                    "title": "sponsored title",
                    "url": "https://www.sponsored.com",
                    "impression_url": "https://www.sponsoredimpression.com",
                    "click_url": "https://www.sponsoredclick.com",
                    "provider": "test provider",
                    "advertiser": "test advertiser",
                    "is_sponsored": True,
                    "icon": "",
                    "score": 0.5,
                }
            ]
        else:
            return []


class NonsponsoredProvider(BaseProvider, DefaultProvider):
    """
    A test nonsponsored provider that only responds to query "nonsponsored".
    """

    def __init__(self) -> None:
        ...

    def enabled_by_default(self) -> bool:
        return True

    def hidden(self) -> bool:
        return False

    async def query(self, q: str) -> list[dict[str, Any]]:
        if q.lower() == "nonsponsored":
            return [
                {
                    "block_id": 0,
                    "full_keyword": "nonsponsored",
                    "title": "nonsponsored title",
                    "url": "https://www.nonsponsored.com",
                    "provider": "test provider",
                    "advertiser": "test nonadvertiser",
                    "is_sponsored": False,
                    "icon": "",
                    "score": 0.5,
                }
            ]
        else:
            return []


def get_providers() -> tuple[dict[str, BaseProvider], list[BaseProvider]]:
    """
    Return a tuple of all the providers and default providers.
    """
    providers = {
        "sponsored-provider": SponsoredProvider(),
        "nonsponsored-provider": NonsponsoredProvider(),
    }
    default_providers = [p for p in providers.values() if p.enabled_by_default()]
    return providers, default_providers
