from typing import Any, Final
import logging

import pdb

from dynaconf.base import LazySettings
from elasticsearch import AsyncElasticsearch, BadRequestError

from merino.configs import settings
from merino.exceptions import BackendError
from merino.providers.suggest.sports import (
    LOGGING_TAG,
)
from merino.providers.suggest.sports.backends.sportsdata.common.data import (
    Sport,
    Event,
)

SUGGEST_ID: Final[str] = "suggest-on-title"
MAX_SUGGESTIONS: Final[int] = settings.providers.sports.max_suggestions
TIMEOUT_MS: Final[str] = f"{settings.providers.sports.es.request_timeout_ms}ms"


# TODO: break this into it's own file?
class ElasticBackendError(BackendError):
    """General error with Elastic Search"""


# TODO: Eventually wrap this with DataStore
class ElasticDataStore:
    platform: str
    client: AsyncElasticsearch
    meta_index: str
    team_index: str
    event_index: str

    def __init__(self, *, settings: LazySettings) -> None:
        """Initialize a connection to ElasticSearch"""
        dsn = settings.providers.sports.es.dsn
        self.client = AsyncElasticsearch(
            dsn, api_key=settings.providers.sports.es.api_key
        )
        # build the index based on the platform.
        self.platform = f"{{lang}}_{settings.sports.get("platform", "sports")}"
        self.meta_index = settings.sports.get("meta_index", f"{self.platform}_meta")
        self.team_index = settings.sports.get("team_index", f"{self.platform}_team")
        self.event_index = settings.sports.get("event_index", f"{self.platform}_event")
        self.data = dict(
            active=[
                sport.strip() for sport in settings.providers.sports.sports.split(",")
            ],
        )
        logging.info(f"{LOGGING_TAG} Initialized Elastic search at {dsn}")

    async def build_indexes(self, settings: LazySettings):
        """ "Indicies are created externally by terraform.
        Build them here for stand-alone and testing reasons.
        """
        dsn = settings.providers.sports.es.dsn
        for language_code in ["en"]:
            for index in [self.meta_index, self.team_index]:
                try:
                    await self.client.indices.create(
                        index=index.format(lang=language_code)
                    )
                except BadRequestError as ex:
                    if ex.error == "resource_already_exists_exception":
                        logging.debug(
                            f"{LOGGING_TAG}🐜 {index.format(lang=language_code)} already exists, skipping"
                        )
                        continue
                    pdb.set_trace()
                    print(ex)

    async def shutdown(self):
        await self.client.close()

    async def search_events(self, q: str, language_code: str) -> list[dict[str, Any]]:
        """Search based on the language and platform template"""
        index_id = self.event_index.format(lang=language_code)

        suggest = {
            SUGGEST_ID: {
                "prefix": q,
                "completion": {"field": "terms", "size": MAX_SUGGESTIONS},
            }
        }

        try:
            query = {"match": {"terms": {"query": q}}}
            res = await self.client.search(
                query=query,
                #                index=index_id,
                #                suggest=suggest,
                timeout=TIMEOUT_MS,
                source_includes=["team_key"],
            )
        except Exception as ex:
            raise BackendError(
                f"{LOGGING_TAG}🚨 Elasticsearch error for {index_id}: {ex}"
            ) from ex

        if "suggest" in res:
            # TODO: filter out duplicate events.
            return [doc for doc in res["suggest"][SUGGEST_ID][0]["options"]]
        else:
            return []

    async def store_events(self, sport: "Sport", language_code: str):
        """Store the events using the calculated terms"""
        pdb.set_trace()
        index = self.event_index.format(lang=language_code)
        for event in sport.events:
            # TODO: convert to bulk.
            body = event.as_json()
            try:
                await self.client.index(
                    index=index,
                    id=str(event.id),
                    body=body,
                )
            except Exception as ex:
                pdb.set_trace()
                print(ex)
                await self.client.update(index=index, id=str(event.id), doc=body)
