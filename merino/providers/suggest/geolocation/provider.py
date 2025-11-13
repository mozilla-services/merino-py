# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""Geolocation provider."""

import logging
from typing import Any

from pydantic import HttpUrl

from merino.providers.suggest.base import (
    BaseProvider,
    BaseSuggestion,
    SuggestionRequest,
)
from merino.providers.suggest.custom_details import CustomDetails, GeolocationDetails

logger = logging.getLogger(__name__)


class Suggestion(BaseSuggestion):
    """Model for geolocation."""


class Provider(BaseProvider):
    """Suggestion provider for geolocation."""

    dummy_url: HttpUrl
    dummy_title: str

    def __init__(
        self,
        name: str = "geolocation",
        enabled_by_default: bool = True,
        dummy_url: str = "https://merino.services.mozilla.com/",
        dummy_title: str = "",
        **kwargs: Any,
    ) -> None:
        self.provider_id = name
        self._enabled_by_default = enabled_by_default
        self.dummy_url = HttpUrl(dummy_url)
        self.dummy_title = dummy_title
        super().__init__(**kwargs)

    async def initialize(self) -> None:
        """Initialize the provider."""
        ...

    def hidden(self) -> bool:  # noqa: D102
        return False

    async def query(self, srequest: SuggestionRequest) -> list[BaseSuggestion]:
        """Provide geolocation suggestions."""
        return [
            Suggestion(
                provider=self.name,
                url=self.dummy_url,
                title=self.dummy_title,
                is_sponsored=False,
                score=0,
                custom_details=CustomDetails(
                    geolocation=GeolocationDetails(
                        country=srequest.geolocation.country_name,
                        region=(
                            srequest.geolocation.region_names[0]
                            if srequest.geolocation.region_names
                            else None
                        ),
                        region_code=(
                            srequest.geolocation.regions[0]
                            if srequest.geolocation.regions
                            else None
                        ),
                        country_code=srequest.geolocation.country,
                        city=srequest.geolocation.city,
                        location=srequest.geolocation.coordinates,
                    )
                ),
            )
        ]

    async def shutdown(self) -> None:
        """Shut down the provider."""
