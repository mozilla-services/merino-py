from typing import Any, Final
import json
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

# TODO: Put this into a separate file?
# from merino.jobs.wikipedia_indexer.settings.v1 import EN_INDEX_SETTINGS

EN_INDEX_SETTINGS: dict = {
    "number_of_replicas": "1",
    "refresh_interval": "-1",
    "number_of_shards": "2",
    "index.lifecycle.name": "enwiki_policy",
    "analysis": {
        "filter": {
            "stop_filter": {
                "type": "stop",
                "remove_trailing": "true",
                "stopwords": "_english_",
            },
            "token_limit": {"type": "limit", "max_token_count": "20"},
            # local_elastic does not understand.
            # "lowercase": {
            #   "name": "nfkc_cf",
            #   "type": "icu_normalizer"},
            "remove_empty": {"type": "length", "min": "1"},
            # local_elastic does not understand.
            # "accentfolding": {"type": "icu_folding"},
        },
        "analyzer": {
            "stop_analyzer_en": {
                "filter": [
                    # "icu_normalizer",
                    "stop_filter",
                    # "accentfolding",
                    "remove_empty",
                    "token_limit",
                ],
                "type": "custom",
                "tokenizer": "standard",
            },
            "plain_search_en": {
                "filter": ["remove_empty", "token_limit", "lowercase"],
                "char_filter": ["word_break_helper"],
                "type": "custom",
                "tokenizer": "whitespace",
            },
            "plain_en": {
                "filter": ["remove_empty", "token_limit", "lowercase"],
                "char_filter": ["word_break_helper"],
                "type": "custom",
                "tokenizer": "whitespace",
            },
            "stop_analyzer_search_en": {
                "filter": [
                    # "icu_normalizer",
                    # "accentfolding",
                    "remove_empty",
                    "token_limit",
                ],
                "type": "custom",
                "tokenizer": "standard",
            },
        },
        "char_filter": {
            "word_break_helper": {
                "type": "mapping",
                "mappings": [
                    "_=>\\u0020",
                    ",=>\\u0020",
                    '"=>\\u0020',
                    "-=>\\u0020",
                    "'=>\\u0020",
                    "\\u2019=>\\u0020",
                    "\\u02BC=>\\u0020",
                    ";=>\\u0020",
                    "\\[=>\\u0020",
                    "\\]=>\\u0020",
                    "{=>\\u0020",
                    "}=>\\u0020",
                    "\\\\=>\\u0020",
                    "\\u00a0=>\\u0020",
                    "\\u1680=>\\u0020",
                    "\\u180e=>\\u0020",
                    "\\u2000=>\\u0020",
                    "\\u2001=>\\u0020",
                    "\\u2002=>\\u0020",
                    "\\u2003=>\\u0020",
                    "\\u2004=>\\u0020",
                    "\\u2005=>\\u0020",
                    "\\u2006=>\\u0020",
                    "\\u2007=>\\u0020",
                    "\\u2008=>\\u0020",
                    "\\u2009=>\\u0020",
                    "\\u200a=>\\u0020",
                    "\\u200b=>\\u0020",
                    "\\u200c=>\\u0020",
                    "\\u200d=>\\u0020",
                    "\\u202f=>\\u0020",
                    "\\u205f=>\\u0020",
                    "\\u3000=>\\u0020",
                    "\\ufeff=>\\u0020",
                ],
            }
        },
    },
}

SUGGEST_ID: Final[str] = "suggest-on-title"
MAX_SUGGESTIONS: Final[int] = settings.providers.sports.max_suggestions
TIMEOUT_MS: Final[str] = f"{settings.providers.sports.es.request_timeout_ms}ms"
INDEX_SETTINGS: dict[str, Any] = {
    "en": EN_INDEX_SETTINGS,
}


# TODO: break this into it's own file?
class ElasticBackendError(BackendError):
    """General error with Elastic Search"""


# TODO: Eventually wrap this with DataStore
class ElasticDataStore:
    platform: str
    client: AsyncElasticsearch
    indices: dict[str, dict]
    languages: list[str]

    def __init__(self, *, settings: LazySettings) -> None:
        """Initialize a connection to ElasticSearch"""
        dsn = settings.providers.sports.es.dsn
        self.client = AsyncElasticsearch(
            dsn, api_key=settings.providers.sports.es.api_key
        )
        self.languages = [
            lang.strip().lower()
            for lang in settings.providers.sports.get("languages", "en").split(",")
        ]
        self.platform = (
            f"{{lang}}_{settings.providers.sports.get("platform", "sports")}"
        )
        # build the index based on the platform.
        self.indices = {
            # "meta": settings.providers.sports.get(
            #     "meta_index", f"{self.platform}_meta"
            # ),
            # "team": settings.providers.sports.get(
            #     "team_index", f"{self.platform}_team"
            # ),
            "event": settings.providers.sports.get(
                "event_index", f"{self.platform}_event"
            ),
        }
        self.data = dict(
            active=[
                sport.strip() for sport in settings.providers.sports.sports.split(",")
            ],
        )
        logging.info(f"{LOGGING_TAG} Initialized Elastic search at {dsn}")

    async def close(self):
        logging.info(f"{LOGGING_TAG} closing...")
        await self.client.close()

    async def build_indexes(self, settings: LazySettings, clear: bool = False):
        """ "Indicies are created externally by terraform.
        Build them here for stand-alone and testing reasons.
        """
        for language_code in self.languages:
            mappings = self.build_mappings(language_code=language_code)
            for idx in ["event"]:
                index = self.indices[idx]
                try:
                    if clear:
                        await self.client.indices.delete(
                            index=index.format(lang=language_code),
                            ignore_unavailable=True,
                        )
                    index = index.format(lang=language_code)
                    logging.debug(f"{LOGGING_TAG} Building index: {index}")
                    resp = await self.client.indices.create(
                        index=(index,),
                        mappings=mappings[idx],
                        settings=INDEX_SETTINGS[language_code],
                    )
                except BadRequestError as ex:
                    if ex.error == "resource_already_exists_exception":
                        logging.debug(
                            f"{LOGGING_TAG}🐜 {index.format(lang=language_code)} already exists, skipping"
                        )
                        continue
                    pdb.set_trace()
                    print(ex)

    def build_mappings(self, language_code: str) -> dict[str, Any]:

        # Note: Since "stop words" are more sport specific, filter these from
        # the "terms" field on load.

        return {
            "event": {
                "dynamic": False,
                "properties": {
                    # The serialized event data
                    "event": {"type": "keyword", "index": False},
                    "ttl": {"type": "integer"},
                    # The non-unique event designator "sport:home:away"
                    "event_key": {"type": "keyword"},
                    # Specify that the terms
                    "terms": {
                        # "type": "completion",
                        # "max_input_length": 100,
                        # "preserve_position_increments": True,
                        # "preserve_separators": True,
                        "type": "text",
                        "analyzer": f"plain_{language_code}",
                        "search_analyzer": f"plain_search_{language_code}",
                    },
                },
            }
        }

    async def shutdown(self):
        await self.client.close()

    async def search_events(self, q: str, language_code: str) -> list[dict[str, Any]]:
        """Search based on the language and platform template"""
        index_id = self.indices["event"].format(lang=language_code)

        suggest = {
            SUGGEST_ID: {
                "match_bool_prefix": q,
                "completion": {"field": "terms", "size": MAX_SUGGESTIONS},
            }
        }

        try:
            query = {"match": {"terms": {"query": q, "operator": "or"}}}
            logging.debug(f"{LOGGING_TAG} Searching {index_id} for `{q}`")
            res = await self.client.search(
                # index=index_id,
                # suggest=suggest,
                query=query,
                timeout=TIMEOUT_MS,
                source_includes=["event"],
            )
        except Exception as ex:
            raise BackendError(
                f"{LOGGING_TAG}🚨 Elasticsearch error for {index_id}: {ex}"
            ) from ex

        if res.get("hits", {}).get("total", {}).get("value", 0) > 0:

            # TODO: filter out duplicate events.
            return [json.loads(doc["_source"]["event"]) for doc in res["hits"]["hits"]]
        else:
            return []

    async def store_events(self, sport: "Sport", language_code: str):
        """Store the events using the calculated terms"""
        index = (self.indices["event"]).format(lang=language_code)
        for event in sport.events:
            # TODO: convert to bulk.
            body = {
                "terms": event.terms,
                "ttl": event.ttl,
                "event_key": event.key(),
                "event": event.as_json(),
            }

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
        await self.client.indices.refresh(index=index)
