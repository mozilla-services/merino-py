# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Provider fakes for the v1 integration test modules."""

import asyncio
from typing import Protocol

from merino.config import settings
from merino.providers import BaseProvider
from merino.providers.base import BaseSuggestion, SuggestionRequest


class QueryCallable(Protocol):
    """Protocol for query functions used by FakeProvider instances."""

    async def __call__(self, srequest: SuggestionRequest) -> list[BaseSuggestion]:
        """Perform a query for the given SuggestionRequest."""
        ...


class NonsponsoredSuggestion(BaseSuggestion):
    """Model for nonsponsored suggestions."""

    block_id: int
    full_keyword: str
    advertiser: str


class SponsoredSuggestion(BaseSuggestion):
    """Model for sponsored suggestions."""

    block_id: int
    full_keyword: str
    advertiser: str
    impression_url: str
    click_url: str


def query_nonsponsored(provider_name: str) -> QueryCallable:
    """Return a QueryCallable for nonsponsored suggestions."""

    async def nonsponsored(srequest: SuggestionRequest) -> list[BaseSuggestion]:
        """Query callable that returns a list with a single NonsponsoredSuggestion."""
        if srequest.query.lower() == "nonsponsored":
            return [
                NonsponsoredSuggestion(
                    block_id=0,
                    full_keyword="nonsponsored",
                    title="nonsponsored title",
                    url="https://www.nonsponsored.com",
                    provider=provider_name,
                    advertiser="test nonadvertiser",
                    is_sponsored=False,
                    icon="https://www.nonsponsoredicon.com",
                    score=0.5,
                )
            ]
        else:
            return []

    return nonsponsored


def query_sponsored(provider_name: str) -> QueryCallable:
    """Return a QueryCallable for sponsored suggestions."""

    async def sponsored(srequest: SuggestionRequest) -> list[BaseSuggestion]:
        """Query callable that returns a list with a single SponsoredSuggestion."""
        if srequest.query.lower() == "sponsored":
            return [
                SponsoredSuggestion(
                    block_id=0,
                    full_keyword="sponsored",
                    title="sponsored title",
                    url="https://www.sponsored.com",
                    impression_url="https://www.sponsoredimpression.com",
                    click_url="https://www.sponsoredclick.com",
                    provider=provider_name,
                    advertiser="test advertiser",
                    is_sponsored=True,
                    icon="https://www.sponsoredicon.com",
                    score=0.5,
                )
            ]
        else:
            return []

    return sponsored


async def raise_error(srequest: SuggestionRequest) -> list[BaseSuggestion]:
    """Raise a RuntimeError instead of returning a list of suggestions."""
    raise RuntimeError(srequest.query)


class FakeProvider(BaseProvider):
    """Fake provider for integration tests."""

    def __init__(
        self,
        *,
        name: str,
        enabled_by_default: bool,
        hidden: bool,
        query_callable: QueryCallable,
        query_timeout_sec: float = settings.runtime.query_timeout_sec,
        sleep_before_sec: float = 0.0,
    ) -> None:
        super().__init__()
        self._name = name
        self._hidden = hidden
        self._query_callable = query_callable
        self._enabled_by_default = enabled_by_default
        self._query_timeout_sec = query_timeout_sec
        self._sleep_before_sec = sleep_before_sec

    async def initialize(self) -> None:
        """Initialize method for the fake provider."""
        ...

    async def query(self, srequest: SuggestionRequest) -> list[BaseSuggestion]:
        """Run the query callable for this fake provider."""
        if self._sleep_before_sec:
            await asyncio.sleep(self._sleep_before_sec)

        return await self._query_callable(srequest=srequest)

    def hidden(self) -> bool:
        """Return a boolean indicating whether the provider is hidden."""
        return self._hidden

    @property
    def enabled_by_default(self) -> bool:
        """Return a boolean indicating whether the provider is enabled."""
        return self._enabled_by_default


class ProviderFactory:
    """Class that holds static methods for creating various fake providers."""

    @staticmethod
    def corrupt(enabled_by_default: bool = True) -> FakeProvider:
        """Return a new corrupt fake provider."""
        return FakeProvider(
            name="corrupted",
            enabled_by_default=enabled_by_default,
            hidden=False,
            query_callable=raise_error,
        )

    @staticmethod
    def hidden(enabled_by_default: bool = True) -> FakeProvider:
        """Return a new hidden fake provider."""
        return FakeProvider(
            name="hidden",
            enabled_by_default=enabled_by_default,
            hidden=True,
            query_callable=raise_error,
        )

    @staticmethod
    def nonsponsored(enabled_by_default: bool = True) -> FakeProvider:
        """Return a new nonsponsored fake provider."""
        provider_name = "non-sponsored"

        return FakeProvider(
            name=provider_name,
            enabled_by_default=enabled_by_default,
            hidden=False,
            query_callable=query_nonsponsored(provider_name),
        )

    @staticmethod
    def sponsored(enabled_by_default: bool = True) -> FakeProvider:
        """Return a new sponsored fake provider."""
        provider_name = "sponsored"

        return FakeProvider(
            name=provider_name,
            enabled_by_default=enabled_by_default,
            hidden=False,
            query_callable=query_sponsored(provider_name),
        )

    @staticmethod
    def timeout_sponsored(enabled_by_default: bool = True) -> FakeProvider:
        """Return a new sponsored fake provider that sleeps."""
        provider_name = "timedout-sponsored"
        return FakeProvider(
            name=provider_name,
            enabled_by_default=enabled_by_default,
            hidden=False,
            query_callable=query_sponsored(provider_name),
            sleep_before_sec=settings.runtime.query_timeout_sec * 2,
        )

    @staticmethod
    def timeout_tolerant_sponsored(
        enabled_by_default: bool = True,
    ) -> FakeProvider:
        """Return a new sponsored fake provider with a higher timeout that sleeps."""
        provider_name = "timedout-tolerant-sponsored"
        return FakeProvider(
            name=provider_name,
            enabled_by_default=enabled_by_default,
            hidden=False,
            query_callable=query_sponsored(provider_name),
            sleep_before_sec=settings.runtime.query_timeout_sec * 2,
            query_timeout_sec=settings.runtime.query_timeout_sec * 4,
        )
