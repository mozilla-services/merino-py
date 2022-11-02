# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import asyncio
from typing import Any, Callable, Coroutine

import pytest

from merino.main import app
from merino.providers import get_providers
from merino.providers.base import BaseProvider, BaseSuggestion, SuggestionRequest

SetupProvidersFixture = Callable[[dict[str, BaseProvider]], None]
TeardownProvidersFixture = Callable[[], None]


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
    """A test sponsored provider that only responds to query 'sponsored'"""

    def __init__(self, enabled_by_default) -> None:
        self._enabled_by_default = enabled_by_default
        self._name = "sponsored"

    async def initialize(self) -> None:
        ...

    def hidden(self) -> bool:
        return False

    async def query(self, srequest: SuggestionRequest) -> list[BaseSuggestion]:
        if srequest.query.lower() == "sponsored":
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
                    is_sponsored=True,
                    icon="https://www.sponsoredicon.com",
                    score=0.5,
                )
            ]
        else:
            return []


class NonsponsoredProvider(BaseProvider):
    """A test nonsponsored provider that only responds to query 'nonsponsored'"""

    def __init__(self, enabled_by_default) -> None:
        self._enabled_by_default = enabled_by_default
        self._name = "non-sponsored"

    async def initialize(self) -> None:
        ...

    def hidden(self) -> bool:
        return False

    async def query(self, srequest: SuggestionRequest) -> list[BaseSuggestion]:
        if srequest.query.lower() == "nonsponsored":
            return [
                NonsponsoredSuggestion(
                    block_id=0,
                    full_keyword="nonsponsored",
                    title="nonsponsored title",
                    url="https://www.nonsponsored.com",
                    provider="test provider",
                    advertiser="test nonadvertiser",
                    is_sponsored=False,
                    icon="https://www.nonsponsoredicon.com",
                    score=0.5,
                )
            ]
        else:
            return []


class CorruptProvider(BaseProvider):
    """A test corrupted provider that raises `RuntimeError` for all queries received"""

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

    async def query(self, srequest: SuggestionRequest) -> list[BaseSuggestion]:
        raise RuntimeError(srequest.query)


def get_provider_factory(
    providers: dict[str, BaseProvider]
) -> Callable[
    ..., Coroutine[Any, Any, tuple[dict[str, BaseProvider], list[BaseProvider]]]
]:
    """Return a callable that builds and initializes the given providers"""

    async def provider_factory() -> tuple[dict[str, BaseProvider], list[BaseProvider]]:
        await asyncio.gather(*[p.initialize() for p in providers.values()])
        default_providers = [p for p in providers.values() if p.enabled_by_default]
        return providers, default_providers

    return provider_factory


@pytest.fixture(name="setup_providers")
def fixture_setup_providers() -> SetupProvidersFixture:
    """Return a function that sets application provider dependency overrides"""

    def setup_providers(providers: dict[str, BaseProvider]) -> None:
        """Set application provider dependency overrides"""
        app.dependency_overrides[get_providers] = get_provider_factory(providers)

    return setup_providers


@pytest.fixture(name="teardown_providers")
def fixture_teardown_providers() -> TeardownProvidersFixture:
    """Return a function that resets application provider dependency overrides"""

    def teardown_providers() -> None:
        """Reset application provider dependency overrides"""
        del app.dependency_overrides[get_providers]

    return teardown_providers
