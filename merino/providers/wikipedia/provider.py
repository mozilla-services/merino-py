"""The provider for the dynamic Wikipedia integration."""
import logging
from typing import Any, Final, Optional

from pydantic import HttpUrl

from merino.config import settings
from merino.exceptions import BackendError
from merino.providers.base import BaseProvider, BaseSuggestion, SuggestionRequest
from merino.providers.wikipedia.backends.protocol import WikipediaBackend

# The packaged Wikipedia icon
ICON: Final[
    str
] = "chrome://activity-stream/content/data/content/tippytop/favicons/wikipedia-org.ico"
ADVERTISER: Final[str] = "dynamic-wikipedia"

logger = logging.getLogger(__name__)


class WikipediaSuggestion(BaseSuggestion):
    """Model for dynamic Wikipedia suggestions.

    For backwards compatibility in Firefox, both `impression_url` and `click_url`
    are set to `None`. Likewise, `block_id` is set to 0 for now.
    """

    full_keyword: str
    advertiser: str
    block_id: int = 0
    impression_url: Optional[HttpUrl] = None
    click_url: Optional[HttpUrl] = None


class Provider(BaseProvider):
    """Suggestion provider for Wikipedia through Elasticsearch."""

    backend: WikipediaBackend
    score: float
    title_block_list: list[str]

    def __init__(
        self,
        backend: WikipediaBackend,
        title_block_list: list[str] = [],
        name: str = "wikipedia",
        enabled_by_default: bool = True,
        query_timeout_sec: float = settings.providers.wikipedia.query_timeout_sec,
        score=settings.providers.wikipedia.score,
        **kwargs: Any,
    ) -> None:
        """Store the given Remote Settings backend on the provider."""
        self.backend = backend
        self.title_block_list = title_block_list
        self._name = name
        self._enabled_by_default = enabled_by_default
        self._query_timeout_sec = query_timeout_sec
        self.score = score
        super().__init__(**kwargs)

    async def initialize(self) -> None:
        """Nothing to initialize."""
        return

    def hidden(self) -> bool:
        """Whether this provider is hidden or not."""
        return False

    async def query(self, srequest: SuggestionRequest) -> list[BaseSuggestion]:
        """Provide suggestion for a given query."""
        try:
            suggestions = await self.backend.search(srequest.query)
        except BackendError as e:
            logger.warning(f"{e}")
            return []

        filtered_suggestions = [
            suggestion
            for suggestion in suggestions
            if suggestion["title"] not in self.title_block_list
        ]

        return [
            WikipediaSuggestion(
                advertiser=ADVERTISER,
                is_sponsored=False,
                icon=ICON,
                score=self.score,
                provider=self.name,
                **suggestion,
            )
            for suggestion in filtered_suggestions
        ]

    async def shutdown(self) -> None:
        """Override the shutdown handler."""
        return await self.backend.shutdown()

    def read_block_list(self, file_path: str) -> list[str]:
        """Read manual block list of blocked titles for manual content moderation."""
        with open(file_path, mode="r") as block_list:
            return [title.strip().lower() for title in block_list.readlines()]
