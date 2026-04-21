"""The Elasticsearch backend for Dynamic Wikipedia."""

import logging
import string
from typing import Any, Final
from urllib.parse import quote
from aiodogstatsd import Client as StatsDClient
from elasticsearch import ApiError

from merino.configs import settings
from merino.exceptions import BackendError
from merino.search.async_elastic import AsyncElasticSearchAdapter
from merino.utils.metrics import ES_SEARCH_METRIC_NAME


SUGGEST_ID: Final[str] = "suggest-on-title"
REQUEST_TIMEOUT_SEC: Final[float] = settings.providers.wikipedia.es_request_timeout_sec
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

    elasticsearch: AsyncElasticSearchAdapter

    def __init__(self, *, api_key: str, url: str, metrics_client: StatsDClient) -> None:
        """Initialize the ElasticBackend.
        Raises a ValueError if URL is incorrectly formatted.

        The client is configured to not retry failures. This is due in part to
        Merino's low latency requirements, and also to avoid undue load
        (e.g. retrying on 429), since searching via suggest is performed
        on each keystroke.
        """
        self.elasticsearch = AsyncElasticSearchAdapter(url=url, api_key=api_key, max_retries=0)
        self._metrics_client = metrics_client
        logging.info("Initialized Elasticsearch with URL")

    async def shutdown(self) -> None:
        """Shut down the connection to the ES cluster."""
        await self.elasticsearch.shutdown()

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

        # Add this if wikipedia gets more than one index; for now it's covered by the provider
        # search count
        # self._metrics_client.increment(f"{ES_SEARCH_METRIC_NAME}.count", tags={"index": index_id})
        try:
            res = await self.elasticsearch.search(
                index=index_id,
                suggest=suggest,
                timeout=REQUEST_TIMEOUT_SEC,
                source_includes=["title"],
            )
        except ApiError as e:
            self._metrics_client.increment(
                f"{ES_SEARCH_METRIC_NAME}.error", tags={"index": index_id, "status": e.meta.status}
            )
            raise BackendError(
                f"Failed to search from Elasticsearch for {language_code}: {e}"
            ) from e
        except Exception as e:
            self._metrics_client.increment(
                f"{ES_SEARCH_METRIC_NAME}.error", tags={"index": index_id, "status": "unknown"}
            )
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
