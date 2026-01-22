"""Builds the elasticsearch index from the export file"""

import json
import logging
import time
from itertools import islice
from typing import Any, Dict, Mapping

from elasticsearch import Elasticsearch
from google.cloud.storage import Blob

from merino.jobs.wikipedia_indexer.filemanager import FileManager
from merino.jobs.wikipedia_indexer.settings import get_settings_for_version
from merino.jobs.wikipedia_indexer.settings.v1 import (
    get_suggest_mapping,
    get_suggest_settings,
)
from merino.jobs.wikipedia_indexer.suggestion import Builder
from merino.jobs.wikipedia_indexer.utils import ProgressReporter

logger = logging.getLogger(__name__)


class Indexer:
    """Index documents from wikimedia search exports into Elasticsearch"""

    QUEUE_MAX_LENGTH = 5000

    queue: list[Mapping[str, Any]]
    suggestion_builder: Builder
    export_file: Blob
    index_version: str
    file_manager: FileManager
    client: Elasticsearch
    category_blocklist: set[str]
    title_blocklist: set[str]

    def __init__(
        self,
        index_version: str,
        category_blocklist: set[str],
        title_blocklist: set[str],
        file_manager: FileManager,
        client: Elasticsearch,
    ):
        self.queue = []
        self.index_version = index_version
        self.file_manager = file_manager
        self.es_client = client
        self.suggestion_builder = Builder(index_version)
        self.category_blocklist = category_blocklist
        self.title_blocklist = {entry.lower() for entry in title_blocklist}

    def index_from_export(self, total_docs: int, elasticsearch_alias: str):
        """Primary indexer method.
        Reads the export file directly from GCS, indexes and swaps index aliases
        """
        language = self.file_manager.language
        logger.info(f"Ensuring latest {language} dump is on GCS")
        latest = self.file_manager.get_latest_gcs()
        if not latest.name:
            raise RuntimeError(f"No exports available on GCS for {language}")

        # parse the index name out of the latest file name
        index_name = self._get_index_name(latest.name)
        logger.info("Ensuring index exists", extra={"index": index_name})

        if self._create_index(index_name):
            logger.info("Start indexing", extra={"index": index_name})
            reporter = ProgressReporter(logger, "Indexing", latest.name, index_name, total_docs)
            indexed = 0
            blocked = 0
            gcs_stream = self.file_manager.stream_from_gcs(latest)
            # The following will chunk `gcs_stream` into a sequence of pairs of
            # (`operator`, `document`), where the first element as the operator
            # (i.e. `index`), the second element as the document data for the
            # operator
            while pair := tuple(islice(gcs_stream, 2)):
                operator, document = pair
                op = json.loads(operator)
                doc = json.loads(document)

                if self._should_filter(doc):
                    blocked += 1
                else:
                    self._enqueue(index_name, (op, doc))
                    indexed += self._index_docs(False)

                # report percent completed
                reporter.report(indexed, blocked)

            # Flush queue after enumerating the export to clear the queue
            self._index_docs(True)
            logger.info(
                "Completed indexing",
                extra={"latest_name": latest.name, "index": index_name},
            )

            # Refresh the new index
            self.es_client.indices.refresh(index=index_name)
            logger.info("Refreshed index", extra={"index": index_name})

            # Flip the alias pointer to the new index and remove the previous index
            self._flip_alias_to_latest(index_name, elasticsearch_alias)
            logger.info(
                "Flipped alias to latest index",
                extra={"index": index_name, "alias": elasticsearch_alias},
            )
        else:
            raise Exception("Could not create the index")

    def _should_filter(self, doc: Dict[str, Any]) -> bool:
        """Return True if we want to filter out this document and not index it.
        Checks for existence of matching categories or title in both title and category blocklists.
        """
        categories: set[str] = set(doc.get("category", []))
        title: str = doc.get("title", "")
        should_filter_category: bool = not self.category_blocklist.isdisjoint(categories)
        should_filter_title: bool = title.lower() in self.title_blocklist if title != "" else True
        return should_filter_category or should_filter_title

    def _enqueue(self, index_name: str, tpl: tuple[Mapping[str, Any], ...]):
        op, doc = self._parse_tuple(index_name, tpl)
        self.queue.append(op)
        self.queue.append(doc)

    def _index_docs(self, force: bool) -> int:
        qlen = len(self.queue)
        item_count = 0
        if qlen > 0 and (qlen >= self.QUEUE_MAX_LENGTH or force):
            try:
                res = self.es_client.bulk(operations=self.queue)
                item_count = len(res.get("items", []))
                items = res.get("items", []) or []
                if "errors" in res and res["errors"]:
                    # Find the first failing item (index/create/update/delete)
                    first_err = None
                    for it in items:
                        action = next(
                            (k for k in ("index", "create", "update", "delete") if k in it),
                            None,
                        )
                        if not action:
                            continue
                        meta = it[action] or {}
                        if meta.get("error"):
                            first_err = {
                                "action": action,
                                "status": meta.get("status"),
                                "index": meta.get("_index"),
                                "id": meta.get("_id"),
                                "error": meta.get("error"),
                            }
                            break

                    logger.error("Bulk operation had errors", extra={"first_error": first_err})

                    raise RuntimeError(f"Bulk failed. First error: {json.dumps(first_err)}")
            except Exception:
                raise
            finally:
                self.queue.clear()
        return item_count

    def _parse_tuple(
        self, index_name: str, tpl: tuple[Mapping[str, Any], ...]
    ) -> tuple[dict[str, Any], ...]:
        op, doc = tpl
        if "index" not in op:
            raise Exception("invalid operation")
        # re use the wikipedia ID (this keeps the indexing
        # operation idempotent from our side)
        id = op["index"]["_id"]
        # TODO make this more generic
        op = {"index": {"_index": index_name, "_id": id}}
        suggestion = self.suggestion_builder.build(id, dict(doc))
        return op, suggestion

    def _get_index_name(self, file_name) -> str:
        timestamp = int(time.time())
        if "/" in file_name:
            _, file_name = file_name.rsplit("/", 1)
        base_name = "-".join(file_name.split("-")[:2])
        return f"{base_name}-{self.index_version}-{timestamp}"

    def _create_index(self, index_name: str) -> bool:
        indices_client = self.es_client.indices
        exists = indices_client.exists(index=index_name)

        version_settings = get_settings_for_version(self.index_version)
        language = self.file_manager.language  # e.g "fr"

        if not exists and version_settings:
            logger.info(f"Creating index for language: {language}")

            res = indices_client.create(
                index=index_name,
                mappings=get_suggest_mapping(language),
                settings=get_suggest_settings(language),
            )
            return bool(res.get("acknowledged", False))

        return False

    def _flip_alias_to_latest(self, current_index: str, alias: str):
        alias = alias.format(version=self.index_version)

        # fetch previous index using alias so we know what to delete
        actions: list[Mapping[str, Any]] = [{"add": {"index": current_index, "alias": alias}}]

        if self.es_client.indices.exists_alias(name=alias):
            indices = self.es_client.indices.get_alias(name=alias)
            for idx in indices:
                logger.info(
                    "adding index to be removed from alias",
                    extra={"index": idx, "alias": alias},
                )
                actions.append({"remove": {"index": idx, "alias": alias}})

        self.es_client.indices.update_aliases(actions=actions)
