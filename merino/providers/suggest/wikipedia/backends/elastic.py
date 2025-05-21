"""The Elasticsearch backend for Dynamic Wikipedia."""

import logging
import string
from typing import Any, Final
from urllib.parse import quote

from elasticsearch import AsyncElasticsearch

from merino.configs import settings
from merino.exceptions import BackendError

SUGGEST_ID: Final[str] = "suggest-on-title"
TIMEOUT_MS: Final[str] = f"{settings.providers.wikipedia.es_request_timeout_ms}ms"
MAX_SUGGESTIONS: Final[int] = settings.providers.wikipedia.es_max_suggestions


INDICES: dict[str, str] = {
    "en": settings.providers.wikipedia.en_es_index,
    "fr": settings.providers.wikipedia.fr_es_index,
    "de": settings.providers.wikipedia.de_es_index,
    "it": settings.providers.wikipedia.it_es_index,
    "pl": settings.providers.wikipedia.pl_es_index,
}

FALLBACK_INDEX: str = INDICES["en"]


class ElasticBackendError(BackendError):
    """Error with Elastic Backend"""


def get_best_keyword(q: str, title: str):
    """Try to get the best autocomplete keyword match from the title. If there are no matches,
    then return the full title as a match. Lowercase everything.
    """
    title = title.lower()
    q = q.strip().lower()
    start_index = title.find(q)
    if start_index < 0:
        return title

    end_index = title.find(" ", start_index + len(q) - 1)
    if end_index < start_index:
        return title[start_index:]

    return title[start_index:end_index].rstrip(string.punctuation)


class ElasticBackend:
    """The client that works with the Elasticsearch backend."""

    client: AsyncElasticsearch

    def __init__(self, *, api_key: str, url: str) -> None:
        """Initialize the ElasticBackend.
        Raises a ValueError if URL is incorrectly formatted.
        """
        self.client = AsyncElasticsearch(url, api_key=api_key)
        logging.info("Initialized Elasticsearch with URL")

    async def shutdown(self) -> None:
        """Shut down the connection to the ES cluster."""
        await self.client.close()

    async def search(self, q: str, language_code: str) -> list[dict[str, Any]]:
        """Search Wikipedia articles from the ES cluster."""
        index_id = INDICES[language_code]

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
                index=index_id,
                suggest=suggest,
                timeout=TIMEOUT_MS,
                source_includes=["title"],
            )
        except Exception as e:
            raise BackendError(
                f"Failed to search from Elasticsearch for {language_code}: {e}"
            ) from e

        if "suggest" in res:
            return [
                self.build_article(q, doc, language_code)
                for doc in res["suggest"][SUGGEST_ID][0]["options"]
            ]
        else:
            return []

    @staticmethod
    def build_article(q: str, doc: dict[str, Any], language_code: str) -> dict[str, Any]:
        """Build a Wikipedia article based on the ES result."""
        title = str(doc["_source"]["title"])
        quoted_title = quote(title.replace(" ", "_"))
        title_prefix = "Wikipédia" if language_code == "fr" else "Wikipedia"

        return {
            "full_keyword": get_best_keyword(q, title),
            "title": f"{title_prefix} - {title}",
            "url": f"https://{language_code}.wikipedia.org/wiki/{quoted_title}",
        }
