import asyncio
from logging import LogRecord
from typing import Any, Callable, Coroutine

from merino.providers.base import BaseProvider, BaseSuggestion


class SponsoredSuggestion(BaseSuggestion):
    """Model for sponsored suggestions."""

    block_id: int
    full_keyword: str
    advertiser: str
    impression_url: str
    click_url: str


class NonsponsoredSuggestion(BaseSuggestion):
    """Model for nonsponsored suggestions."""

    block_id: int
    full_keyword: str
    advertiser: str


class SponsoredProvider(BaseProvider):
    """
    A test sponsored provider that only responds to query "sponsored".
    """

    def __init__(self, enabled_by_default) -> None:
        self._enabled_by_default = enabled_by_default
        self._name = "sponsored"

    async def initialize(self) -> None:
        ...

    def hidden(self) -> bool:
        return False

    async def query(self, q: str) -> list[BaseSuggestion]:
        if q.lower() == "sponsored":
            return [
                SponsoredSuggestion(
                    block_id=0,
                    full_keyword="sponsored",
                    title="sponsored title",
                    url="https://www.sponsored.com",
                    impression_url="https://www.sponsoredimpression.com",
                    click_url="https://www.sponsoredclick.com",
                    provider="test provider",
                    advertiser="test advertiser",
                    icon="https://www.sponsoredicon.com",
                    score=0.5,
                )
            ]
        else:
            return []


class NonsponsoredProvider(BaseProvider):
    """
    A test nonsponsored provider that only responds to query "nonsponsored".
    """

    def __init__(self, enabled_by_default) -> None:
        self._enabled_by_default = enabled_by_default
        self._name = "non-sponsored"

    async def initialize(self) -> None:
        ...

    def hidden(self) -> bool:
        return False

    async def query(self, q: str) -> list[BaseSuggestion]:
        if q.lower() == "nonsponsored":
            return [
                NonsponsoredSuggestion(
                    block_id=0,
                    full_keyword="nonsponsored",
                    title="nonsponsored title",
                    url="https://www.nonsponsored.com",
                    provider="test provider",
                    advertiser="test nonadvertiser",
                    icon="https://www.nonsponsoredicon.com",
                    score=0.5,
                )
            ]
        else:
            return []


class CorruptProvider(BaseProvider):
    """
    A test corrupted provider that raises `RuntimeError` for all queries received.
    """

    def __init__(self) -> None:
        self._name = "corrupted"
        ...

    async def initialize(self) -> None:
        ...

    @property
    def enabled_by_default(self) -> bool:
        return True

    def hidden(self) -> bool:
        return False

    async def query(self, q: str) -> list[BaseSuggestion]:
        raise RuntimeError(q)


def get_provider_factory(
    providers: dict[str, BaseProvider]
) -> Callable[
    ..., Coroutine[Any, Any, tuple[dict[str, BaseProvider], list[BaseProvider]]]
]:
    """Returns a callable that builds and initializes the given providers."""

    async def provider_factory() -> tuple[dict[str, BaseProvider], list[BaseProvider]]:
        await asyncio.gather(*[p.initialize() for p in providers.values()])
        default_providers = [p for p in providers.values() if p.enabled_by_default]
        return providers, default_providers

    return provider_factory


async def get_providers() -> tuple[dict[str, BaseProvider], list[BaseProvider]]:
    """
    Return a tuple of all the providers and default providers.
    """
    return await get_provider_factory(
        {
            "sponsored-provider": SponsoredProvider(enabled_by_default=True),
            "nonsponsored-provider": NonsponsoredProvider(enabled_by_default=True),
        }
    )()


def filter_caplog(records: list[LogRecord], logger_name: str) -> list[LogRecord]:
    """Filter pytest captured log records for a given logger name."""
    return [record for record in records if record.name == logger_name]
