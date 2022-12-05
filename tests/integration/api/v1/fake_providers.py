# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Provider fakes for the v1 integration test modules."""

import asyncio

from merino.config import settings
from merino.providers import BaseProvider
from merino.providers.base import BaseSuggestion, SuggestionRequest


class CorruptProvider(BaseProvider):
    """A test corrupted provider that raises `RuntimeError` for all queries received"""

    def __init__(self) -> None:
        self._name = "corrupted"

    async def initialize(self) -> None:
        """Initialize method for the CorruptProvider."""
        ...

    @property
    def enabled_by_default(self) -> bool:
        """Return boolean indicating whether the provider is enabled."""
        return True

    def hidden(self) -> bool:
        """Return boolean indicating whether the provider is hidden."""
        return False

    async def query(self, srequest: SuggestionRequest) -> list[BaseSuggestion]:
        """Query against the CorruptProvider."""
        raise RuntimeError(srequest.query)


class HiddenProvider(BaseProvider):
    """A provider fake intended for test with a 'hidden' property set to return True."""

    def __init__(self, enabled_by_default) -> None:
        self._enabled_by_default = enabled_by_default
        self._name = "hidden"

    async def initialize(self) -> None:
        """Initialize method for the HiddenProvider."""
        ...

    def hidden(self) -> bool:
        """Return boolean indicating whether the provider is hidden."""
        return True

    async def query(self, srequest: SuggestionRequest) -> list[BaseSuggestion]:
        """Query against the HiddenProvider."""
        raise RuntimeError(srequest.query)


class NonsponsoredSuggestion(BaseSuggestion):
    """Model for nonsponsored suggestions."""

    block_id: int
    full_keyword: str
    advertiser: str


class NonsponsoredProvider(BaseProvider):
    """A test nonsponsored provider that only responds to query 'nonsponsored'"""

    def __init__(self, enabled_by_default) -> None:
        self._enabled_by_default = enabled_by_default
        self._name = "non-sponsored"

    async def initialize(self) -> None:
        """Initialize method for the NonsponsoredProvider."""
        ...

    def hidden(self) -> bool:
        """Return boolean indicating whether the provider is hidden."""
        return False

    async def query(self, srequest: SuggestionRequest) -> list[BaseSuggestion]:
        """Query against the NonsponsoredProvider."""
        if srequest.query.lower() == "nonsponsored":
            return [
                NonsponsoredSuggestion(
                    block_id=0,
                    full_keyword="nonsponsored",
                    title="nonsponsored title",
                    url="https://www.nonsponsored.com",
                    provider=self.name,
                    advertiser="test nonadvertiser",
                    is_sponsored=False,
                    icon="https://www.nonsponsoredicon.com",
                    score=0.5,
                )
            ]
        else:
            return []


class SponsoredSuggestion(BaseSuggestion):
    """Model for sponsored suggestions."""

    block_id: int
    full_keyword: str
    advertiser: str
    impression_url: str
    click_url: str


class SponsoredProvider(BaseProvider):
    """A test sponsored provider that only responds to query 'sponsored'"""

    def __init__(self, enabled_by_default) -> None:
        self._enabled_by_default = enabled_by_default
        self._name = "sponsored"

    async def initialize(self) -> None:
        """Initialize method for the SponsoredProvider."""
        ...

    def hidden(self) -> bool:
        """Return boolean indicating whether the provider is hidden."""
        return False

    async def query(self, srequest: SuggestionRequest) -> list[BaseSuggestion]:
        """Query against the SponsoredProvider."""
        if srequest.query.lower() == "sponsored":
            return [
                SponsoredSuggestion(
                    block_id=0,
                    full_keyword="sponsored",
                    title="sponsored title",
                    url="https://www.sponsored.com",
                    impression_url="https://www.sponsoredimpression.com",
                    click_url="https://www.sponsoredclick.com",
                    provider=self.name,
                    advertiser="test advertiser",
                    is_sponsored=True,
                    icon="https://www.sponsoredicon.com",
                    score=0.5,
                )
            ]
        else:
            return []


class TimeoutSponsoredProvider(SponsoredProvider):
    """A sponsored provider that always returns the result in
    `2 * settings.runtime.query_timeout_sec`
    """

    def __init__(self, enabled_by_default) -> None:
        super().__init__(enabled_by_default=enabled_by_default)
        self._name = "timedout-sponsored"

    async def query(self, srequest: SuggestionRequest) -> list[BaseSuggestion]:
        """Query against the TimeoutSponsoredProvider."""
        await asyncio.sleep(settings.runtime.query_timeout_sec * 2)
        return await super().query(srequest)


class TimeoutTolerantSponsoredProvider(TimeoutSponsoredProvider):
    """A timeout tolerant sponsored provider."""

    def __init__(self, enabled_by_default) -> None:
        super().__init__(enabled_by_default=enabled_by_default)
        self._name = "timedout-tolerant-sponsored"
        # It can tolerate for 4x of the default query timeout
        self._query_timeout_sec = settings.runtime.query_timeout_sec * 4
