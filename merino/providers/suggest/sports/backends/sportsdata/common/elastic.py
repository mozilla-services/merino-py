"""Store and retrieve Sports information from ElasticSearch"""

import json
import logging
from abc import abstractmethod
from datetime import datetime, timezone
from typing import Any, Final


from dynaconf.base import LazySettings
from elasticsearch import AsyncElasticsearch, BadRequestError, ConflictError, helpers

from merino.configs import settings
from merino.exceptions import BackendError
from merino.providers.suggest.sports import (
    LOGGING_TAG,
)
from merino.providers.suggest.sports.backends.sportsdata.common import GameStatus
from merino.providers.suggest.sports.backends.sportsdata.common.data import (
    Sport,
)
from merino.providers.suggest.sports.backends.sportsdata.common.error import (
    SportsDataError,
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


class ElasticDataStore:
    """General Elastic Data Store"""

    client: AsyncElasticsearch

    def __init__(
        self,
        *,
        dsn: str,
        api_key: str,
    ):
        """Create a core instance of elastic search"""
        self.client = AsyncElasticsearch(dsn, api_key=api_key)

    async def shutdown(self) -> None:
        """Politely close the data connection. Not strictly required, but python
        may complain.
        """
        logging.info(f"{LOGGING_TAG} closing...")
        await self.client.close()

    @abstractmethod
    def build_mappings(self, language_code: str) -> dict[str, Any]:
        """Construct the mappings to be used by Elastic search.
        This should be done by the package that is storing data to Elastic search.
        See: https://www.elastic.co/docs/manage-data/data-store/mapping

        A mapping is a structured dict with a format similar to:

        ```python
        return {
            # This key is the central index that the mapping will refer to.
            "event": {
                # Do not dynamically map values. Since we want to be explicit,
                # we'll turn that off, otherwise, elastic will try to figure out
                # each field's type
                "dynamic": False,
                # This is the list of field properties and their types.
                # See https://www.elastic.co/docs/manage-data/data-store/mapping/explicit-mapping
                "properties": {
                    # The serialized event data
                    "event": {"type": "keyword", "index": False},
                    "date": {"type": "integer"},
                    "sport": {"type": "keyword"},
                    "status_type": {"type": "keyword"},
                    "expiry": {"type": "integer"},
                    # This is a complex type that specifies the search analyzer from `build_indexes`
                    "terms": {
                        "type": "text",
                        "analyzer": f"plain_{language_code}",
                        "search_analyzer": f"plain_search_{language_code}",
                    },
                },
            }
        }

        """

    @abstractmethod
    async def build_indexes(self, settings: LazySettings, clear: bool = False):
        """Build the local indexes required.

        The `index` contains the general settings and definitions that elastic
        will use to create the database. These _may_ be defined externally, however
        local testing or dev installs will still need this data.
        """


class SportsDataStore(ElasticDataStore):
    """Wrapper for the Elastic Search data store.

    Eventually, this should be moved into a generic `utils` directory.
    """

    platform: str
    client: AsyncElasticsearch
    index_map: dict[str, str]
    languages: list[str]

    def __init__(
        self,
        *,
        dsn: str,
        api_key: str,
        languages: list[str],
        platform: str,
        index_map: dict[str, str],
        settings: LazySettings,
    ) -> None:
        """Initialize a connection to ElasticSearch"""
        super().__init__(dsn=dsn, api_key=api_key)
        self.languages = languages
        self.platform = platform
        # build the index based on the platform.
        self.index_map = index_map
        logging.info(f"{LOGGING_TAG} Initialized Elastic search at {dsn}")

    # === Less generic methods

    async def build_indexes(self, settings: LazySettings, clear: bool = False):
        """Build the indices here for stand-alone and testing reasons.

        Normally, these are built using terraform.
        """
        for language_code in self.languages:
            mappings = self.build_mappings(language_code=language_code)
            for idx, index in self.index_map.items():
                try:
                    if clear:
                        await self.client.indices.delete(
                            index=index.format(lang=language_code),
                            ignore_unavailable=True,
                        )
                    index = index.format(lang=language_code)
                    logging.debug(f"{LOGGING_TAG} Building index: {index}")
                    await self.client.indices.create(
                        index=index,
                        mappings=mappings[idx],
                        settings=INDEX_SETTINGS[language_code],
                    )
                except BadRequestError as ex:
                    if ex.error == "resource_already_exists_exception":
                        logging.debug(
                            f"{LOGGING_TAG}🐜 {index.format(lang=language_code)} already exists, skipping"
                        )
                        continue
                    raise SportsDataError(f"Could not create {index}") from ex

    def build_mappings(self, language_code: str) -> dict[str, Any]:
        """Construct the mappings to be used by Elastic search.
        This should be done by the package that is storing data to Elastic search.
        """
        # Note: Since "stop words" are more sport specific, filter these from
        # the "terms" field on load.
        return {
            "event": {
                "dynamic": False,
                "properties": {
                    # The serialized event data
                    "event": {"type": "keyword", "index": False},
                    "status_type": {"type": "keyword"},
                    "expiry": {"type": "integer"},
                    "sport": {"type": "keyword"},
                    "date": {"type": "integer"},
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

    async def prune(self, expiry: int | None = None, language_code: str = "en") -> bool:
        """Remove data that has expired."""
        utc_now = expiry or int(datetime.now(tz=timezone.utc).timestamp())
        for index_pattern in self.index_map.values():
            index = index_pattern.format(lang=language_code)
            query = {"range": {"expiry": {"lte": utc_now}}}
            try:
                res = await self.client.delete_by_query(
                    index=index, query=query, timeout=TIMEOUT_MS
                )
                logging.info(f"{LOGGING_TAG}✂️ Deleted {res.get("deleted")}")
            except ConflictError:
                # The ConflictError returns a string that is not quite JSON, so we can't
                # parse it
                logging.info(
                    f"{LOGGING_TAG} Encountered conflict error, ignoring for now"
                )
        return True

    async def search_events(self, q: str, language_code: str) -> dict[str, dict]:
        """Search based on the language and platform template"""
        index_id = self.index_map["event"].format(lang=language_code)
        utc_now = int(datetime.now(tz=timezone.utc).timestamp())

        try:
            query = {
                "bool": {
                    "must": [{"match": {"terms": {"query": q, "operator": "or"}}}],
                    "must_not": [{"range": {"expiry": {"lt": utc_now}}}],
                }
            }

            logging.debug(f"{LOGGING_TAG} Searching {index_id} for `{q}`")

            res = await self.client.search(
                query=query,
                # sort=["sport", "date"],
                timeout=TIMEOUT_MS,
                source_includes=["event"],
            )
        except Exception as ex:
            raise BackendError(f"Elasticsearch error for {index_id}") from ex
        if res.get("hits", {}).get("total", {}).get("value", 0) > 0:
            # filter sport for prev, current, next
            filter: dict[str, dict] = {}
            for doc in res["hits"]["hits"]:
                event = json.loads((doc["_source"]["event"]))
                # Add the elastic search score as a baseline score for the return result.
                event["_score"] = doc.get("_score", 0)
                sport = event["sport"]
                if sport not in filter:
                    filter[sport] = {}
                status = GameStatus.parse(event["status"])
                if status.is_final():
                    filter[sport]["previous"] = event
                # If only show the next upcoming game.
                if status.is_scheduled() and "next" not in filter[sport]:
                    filter[sport]["next"] = event
                if status.is_in_progress():
                    # remove the previous game info because we have a current one.
                    del filter[sport]["previous"]
                    filter[sport]["current"] = event
            return filter
        else:
            return {}

    async def store_events(self, sport: "Sport", language_code: str):
        """Store the events using the calculated terms"""
        actions = []

        index = (self.index_map["event"]).format(lang=language_code)

        for event in sport.events.values():
            action = {
                "_index": index,
                "_id": event.id,
                "_source": {
                    "sport": event.sport,
                    "terms": event.terms,
                    "date": event.date.timestamp(),
                    "expiry": event.expiry,
                    "id": event.id,
                    "event_key": event.key(),
                    "status_type": event.status.status_type(),
                    "event": event.as_json(),
                },
            }
            actions.append(action)

            try:
                await helpers.async_bulk(client=self.client, actions=actions)
            except Exception as ex:
                print(ex)
        await self.client.indices.refresh(index=index)
