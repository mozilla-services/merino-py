"""The provider for the dynamic Wikipedia integration."""
import logging
from typing import Any, Final, Optional, Protocol
from urllib.parse import quote

from elasticsearch import AsyncElasticsearch
from pydantic import HttpUrl

from merino.config import settings
from merino.providers.base import BaseProvider, BaseSuggestion, SuggestionRequest

logger = logging.getLogger(__name__)

# The Index ID in Elasticsearch cluster.
INDEX_ID: Final[str] = settings.providers.wikipedia.es_index
SCORE: Final[float] = settings.providers.wikipedia.score
# The packaged Wikipedia icon
ICON: Final[
    str
] = "chrome://activity-stream/content/data/content/tippytop/favicons/wikipedia-org.ico"
SUGGEST_ID: Final[str] = "suggest-on-title"
TIMEOUT_MS: Final[str] = f"{settings.providers.wikipedia.es_request_timeout_ms}ms"
MAX_SUGGESTIONS: Final[int] = settings.providers.wikipedia.es_max_suggestions
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


class WikipediaBackend(Protocol):
    """Protocol for a Wikipedia backend that this provider depends on.

    Note: This only defines the methods used by the provider. The actual backend
    might define additional methods and attributes which this provider doesn't
    directly depend on.
    """

    async def shutdown(self) -> None:  # pragma: no cover
        """Shut down connection to the backend"""
        ...

    async def search(self, q: str) -> list[dict[str, Any]]:  # pragma: no cover
        """Search suggestions for a given query from the backend."""
        ...


class TestBackend:  # pragma: no cover
    """A mock backend for testing."""

    async def shutdown(self) -> None:
        """Nothing to shut down."""
        return None

    async def search(self, _: str) -> list[dict[str, Any]]:
        """Return an empty list."""
        return []


class TestEchoBackend:
    """A mock backend for testing.

    It returns the exact same query as the search result.
    """

    async def shutdown(self) -> None:
        """Nothing to shut down."""
        return None

    async def search(self, q: str) -> list[dict[str, Any]]:
        """Echoing the query as the single suggestion."""
        return [
            {
                "full_keyword": q,
                "title": q,
                "url": f"""https://en.wikipedia.org/wiki/{quote(q.replace(" ", "_"))}""",
            }
        ]


class ElasticBackend:
    """The client that works with the Elasticsearch backend."""

    client: AsyncElasticsearch

    def __init__(self, hosts: str) -> None:
        """Initialize."""
        self.client = AsyncElasticsearch(hosts=hosts)

    async def shutdown(self) -> None:
        """Shut down the connection to the ES cluster."""
        await self.client.close()

    async def search(self, q: str) -> list[dict[str, Any]]:
        """Search suggestions for a given query from the ES cluster."""
        suggest = {
            SUGGEST_ID: {
                "prefix": q,
                "completion": {
                    "field": "suggest",
                    "size": MAX_SUGGESTIONS,
                },
            }
        }

        try:
            res = await self.client.search(
                index=INDEX_ID,
                suggest=suggest,
                timeout=TIMEOUT_MS,
                source_includes=["title"],
            )
        except Exception as e:
            logger.warning(f"Failed to search from ES: {e}")
            return []

        if "suggest" in res:
            return [
                self.build_article(doc)
                for doc in res["suggest"][SUGGEST_ID][0]["options"]
            ]
        else:
            return []

    @staticmethod
    def build_article(doc: dict[str, Any]) -> dict[str, Any]:
        """Build a wikipedia article based on the ES result."""
        title = str(doc["_source"]["title"])
        quoted_title = quote(title.replace(" ", "_"))
        return {
            "full_keyword": title,
            "title": title,
            "url": f"https://en.wikipedia.org/wiki/{quoted_title}",
        }


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
