"""The provider for the dynamic Wikipedia integration."""

import logging
from typing import Any, Final

from pydantic import HttpUrl

from merino.configs import settings
from merino.exceptions import BackendError
from merino.providers.suggest.base import BaseProvider, BaseSuggestion, SuggestionRequest, Category
from merino.providers.suggest.wikipedia.backends.protocol import WikipediaBackend
from merino.providers.suggest.wikipedia.backends.utils import get_language_code

# The Wikipedia icon backed by Merino's image CDN.
# TODO: Use a better way to fetch this icon URL instead of hardcoding it here.
ICON: Final[str] = (
    "https://merino-images.services.mozilla.com/favicons/"
    "4c8bf96d667fa2e9f072bdd8e9f25c8ba6ba2ad55df1af7d9ea0dd575c12abee_1313.png"
)
ADVERTISER: Final[str] = "dynamic-wikipedia"
BLOCK_ID: Final[int] = 0

logger = logging.getLogger(__name__)


class WikipediaSuggestion(BaseSuggestion):
    """Model for dynamic Wikipedia suggestions.

    For backwards compatibility in Firefox, both `impression_url` and `click_url`
    are set to `None`. Likewise, `block_id` is set to 0 for now.
    """

    full_keyword: str
    advertiser: str
    block_id: int
    impression_url: HttpUrl | None = None
    click_url: HttpUrl | None = None


class Provider(BaseProvider):
    """Suggestion provider for Wikipedia through Elasticsearch."""

    backend: WikipediaBackend
    score: float
    title_block_list: set[str]

    def __init__(
        self,
        backend: WikipediaBackend,
        title_block_list: set[str],
        name: str = "wikipedia",
        enabled_by_default: bool = True,
        query_timeout_sec: float = settings.providers.wikipedia.query_timeout_sec,
        score=settings.providers.wikipedia.score,
        **kwargs: Any,
    ) -> None:
        """Store the given Remote Settings backend on the provider."""
        self.backend = backend
        # Ensures block list checks are case insensitive.
        self.title_block_list = {entry.lower() for entry in title_block_list}
        self._name = name
        self._enabled_by_default = enabled_by_default
        self._query_timeout_sec = query_timeout_sec
        self.score = score
        super().__init__(**kwargs)

    async def initialize(self) -> None:
        """Initialize Wikipedia provider."""
        return

    def hidden(self) -> bool:  # noqa: D102
        """Whether this provider is hidden or not."""
        return False

    async def query(self, srequest: SuggestionRequest) -> list[BaseSuggestion]:
        """Provide suggestion for a given query."""
        try:
            languages: list[str] = srequest.languages if srequest.languages else []
            language_code = get_language_code(languages)
            suggestions = await self.backend.search(srequest.query, language_code)
        except BackendError as e:
            logger.warning(f"{e}")
            return []

        return [
            WikipediaSuggestion(
                block_id=BLOCK_ID,
                advertiser=ADVERTISER,
                is_sponsored=False,
                icon=ICON,
                score=self.score,
                provider=self.name,
                categories=[Category.Education],
                **suggestion,
            )
            for suggestion in suggestions
            # Ensures titles that are in the block list are not returned as suggestions.
            if suggestion["title"].lower() not in self.title_block_list
        ]

    async def shutdown(self) -> None:
        """Override the shutdown handler."""
        return await self.backend.shutdown()
