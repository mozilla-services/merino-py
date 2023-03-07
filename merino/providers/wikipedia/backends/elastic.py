"""The Elasticsearch backend for Dynamic Wikipedia."""
import logging
from typing import Any, Final, Optional
from urllib.parse import quote

from elasticsearch import AsyncElasticsearch

from merino.config import settings
from merino.exceptions import BackendError

# The Index ID in Elasticsearch cluster.
INDEX_ID: Final[str] = settings.providers.wikipedia.es_index
SUGGEST_ID: Final[str] = "suggest-on-title"
TIMEOUT_MS: Final[str] = f"{settings.providers.wikipedia.es_request_timeout_ms}ms"
MAX_SUGGESTIONS: Final[int] = settings.providers.wikipedia.es_max_suggestions


class ElasticBackendError(BackendError):
    """Error with Elastic Backend"""


class ElasticBackend:
    """The client that works with the Elasticsearch backend."""

    client: AsyncElasticsearch

    def __init__(
        self, *, api_key: str, url: Optional[str] = None, cloud_id: Optional[str] = None
    ) -> None:
        """Initialize."""
        if url:
            self.client = AsyncElasticsearch(url, api_key=api_key)
            logging.info("Initialized Elasticsearch with URL")
        elif cloud_id:
            self.client = AsyncElasticsearch(cloud_id=cloud_id, api_key=api_key)
            logging.info("Initialized Elasticsearch with Cloud ID")
        else:
            raise ElasticBackendError(
                "Require one of {url, cloud_id} to initialize Elasticsearch client."
            )

    async def shutdown(self) -> None:
        """Shut down the connection to the ES cluster."""
        await self.client.close()

    async def search(self, q: str) -> list[dict[str, Any]]:
        """Search Wikipedia articles from the ES cluster."""
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
            raise BackendError(f"Failed to search from Elasticsearch: {e}") from e

        if "suggest" in res:
            return [
                self.build_article(doc)
                for doc in res["suggest"][SUGGEST_ID][0]["options"]
            ]
        else:
            return []

    @staticmethod
    def build_article(doc: dict[str, Any]) -> dict[str, Any]:
        """Build a Wikipedia article based on the ES result."""
        title = str(doc["_source"]["title"])
        quoted_title = quote(title.replace(" ", "_"))
        return {
            "full_keyword": title,
            "title": title,
            "url": f"https://en.wikipedia.org/wiki/{quoted_title}",
        }
