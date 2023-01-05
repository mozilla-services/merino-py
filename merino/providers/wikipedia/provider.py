"""The provider for the dynamic Wikipedia integration."""
from typing import Any, Final, Optional

from pydantic import HttpUrl

from merino.config import settings
from merino.providers.base import BaseProvider, BaseSuggestion, SuggestionRequest
from merino.providers.wikipedia.backends.protocol import WikipediaBackend

# The Index ID in Elasticsearch cluster.
SCORE: Final[float] = settings.providers.wikipedia.score
# The packaged Wikipedia icon
ICON: Final[
    str
] = "chrome://activity-stream/content/data/content/tippytop/favicons/wikipedia-org.ico"
ADVERTISER: Final[str] = "dynamic-wikipedia"


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

    def __init__(
        self,
        backend: WikipediaBackend,
        name: str = "wikipedia",
        enabled_by_default: bool = True,
        **kwargs: Any,
    ) -> None:
        """Store the given Remote Settings backend on the provider."""
        self.backend = backend
        self._name = name
        self._enabled_by_default = enabled_by_default
        super().__init__(**kwargs)

    async def initialize(self) -> None:
        """Nothing to initialize."""
        return

    def hidden(self) -> bool:
        """Whether this provider is hidden or not."""
        return False

    async def query(self, srequest: SuggestionRequest) -> list[BaseSuggestion]:
        """Provide suggestion for a given query."""
        suggestions = await self.backend.search(srequest.query)
        return [
            WikipediaSuggestion(
                advertiser=ADVERTISER,
                is_sponsored=False,
                icon=ICON,
                score=SCORE,
                provider=self.name,
                **suggestion,
            )
            for suggestion in suggestions
        ]

    async def shutdown(self) -> None:
        """Override the shutdown handler."""
        return await self.backend.shutdown()
