"""Wikimedia Picture of the Day provider."""

import logging
import aiodogstatsd

from pydantic import BaseModel, Field, HttpUrl

from merino.providers.rss.base import BaseRssProvider

logger = logging.getLogger(__name__)


class Potd(BaseModel):
    """Model for the Wikimedia Picture of the Day."""

    title: str = Field(description="Title of the picture of the day.")
    image_url: str = Field(description="URL of the picture of the day image.")


class WikimediaPotdProvider(BaseRssProvider):
    """Provider for the Wikimedia Picture of the Day feed."""

    backend: None
    metrics_client: aiodogstatsd.Client
    url: HttpUrl
    manifest_data: None

    def __init__(
        self,
        backend: None,
        metrics_client: aiodogstatsd.Client,
        name: str,
        query_timeout_sec: float,
        enabled_by_default: bool = False,
    ) -> None:
        self.backend = None
        self.metrics_client = metrics_client
        self._name = name
        self._query_timeout_sec = query_timeout_sec
        self._enabled_by_default = enabled_by_default
        self.url = HttpUrl("https://merino.services.mozilla.com/")
        self.manifest_data = None

        super().__init__()

    async def initialize(self) -> None:
        """Initialize the provider."""

    async def get_picture_of_the_day(self) -> Potd:
        """Return the current Wikimedia Picture of the Day."""
        return Potd(title="", image_url="")

    async def shutdown(self) -> None:
        """Shut down the provider."""
