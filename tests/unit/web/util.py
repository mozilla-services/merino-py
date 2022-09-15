import asyncio
from logging import LogRecord
from typing import Any, Callable, Coroutine

from merino.providers.base import BaseProvider


class SponsoredProvider(BaseProvider):
    """
    A test sponsored provider that only responds to query "sponsored".
    """

    def __init__(self) -> None:
        ...

    async def initialize(self) -> None:
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
                    "icon": "https://www.sponsoredicon.com",
                    "score": 0.5,
                }
            ]
        else:
            return []


class NonsponsoredProvider(BaseProvider):
    """
    A test nonsponsored provider that only responds to query "nonsponsored".
    """

    def __init__(self) -> None:
        ...

    async def initialize(self) -> None:
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
                    "icon": "https://www.nonsponsoredicon.com",
                    "score": 0.5,
                }
            ]
        else:
            return []


class CorruptProvider(BaseProvider):
    """
    A test corrupted provider that raises `RuntimeError` for all queries received.
    """

    def __init__(self) -> None:
        ...

    async def initialize(self) -> None:
        ...

    def enabled_by_default(self) -> bool:
        return True

    def hidden(self) -> bool:
        return False

    async def query(self, q: str) -> list[dict[str, Any]]:
        raise RuntimeError(q)


def get_provider_factory(
    providers: dict[str, BaseProvider]
) -> Callable[
    ..., Coroutine[Any, Any, tuple[dict[str, BaseProvider], list[BaseProvider]]]
]:
    """Returns a callable that builds and initializes the given providers."""

    async def provider_factory() -> tuple[dict[str, BaseProvider], list[BaseProvider]]:
        await asyncio.gather(*[p.initialize() for p in providers.values()])
        default_providers = [p for p in providers.values() if p.enabled_by_default()]
        return providers, default_providers

    return provider_factory


async def get_providers() -> tuple[dict[str, BaseProvider], list[BaseProvider]]:
    """
    Return a tuple of all the providers and default providers.
    """
    return await get_provider_factory(
        {
            "sponsored-provider": SponsoredProvider(),
            "nonsponsored-provider": NonsponsoredProvider(),
        }
    )()


def filter_caplog(records: list[LogRecord], logger_name: str) -> list[LogRecord]:
    """Filter pytest captured log records for a given logger name."""
    return [record for record in records if record.name == logger_name]
