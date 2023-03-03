"""Builds the elasticsearch index from the export file"""
import json
import logging
import time
from typing import Any, Generator, Mapping

from elasticsearch import Elasticsearch
from google.cloud.storage import Blob

from merino.jobs.wikipedia_indexer.filemanager import FileManager
from merino.jobs.wikipedia_indexer.settings import get_settings_for_version
from merino.jobs.wikipedia_indexer.suggestion import Builder
from merino.jobs.wikipedia_indexer.util import ProgressReporter

logger = logging.getLogger(__name__)


def stream_bulk(
    stream: Generator[str, None, None]
) -> Generator[tuple[str, str], None, None]:
    """Aggregate each bulk component into a single yield. Each bulk component consists of:
    1. First line as the operator (ie. `index`)
    2. Second line as the document data for the operator.

    Since we're only expecting index lines, each bulk component will always consist of 2 lines.
    """
    operation = None
    for row in stream:
        if operation is None:
            operation = row
        else:
            # NOTE: Mypy thinks that the following line is unreachable,
            # even though they actually are reachable.
            yield operation, row  # type: ignore
            operation = None


class Indexer:
    """Index documents from wikimedia search exports into Elasticsearch"""

    QUEUE_MAX_LENGTH = 5000

    queue: list[Mapping[str, Any]]
    suggestion_builder: Builder
    export_file: Blob
    index_version: str
    file_manager: FileManager
    client: Elasticsearch
    blocklist: set[str]

    def __init__(
        self,
        index_version: str,
        blocklist: set[str],
        file_manager: FileManager,
        client: Elasticsearch,
    ):
        self.queue = []
        self.index_version = index_version
        self.file_manager = file_manager
        self.es_client = client
        self.suggestion_builder = Builder(index_version)
        self.blocklist = blocklist

    def index_from_export(self, total_docs: int, elasticsearch_alias: str):
        """Primary indexer method.
        Reads the export file directly from GCS, indexes and swaps index aliases
        """
        logger.info("Ensuring latest dump is on GCS")
        latest = self.file_manager.get_latest_gcs()
        if not latest.name:
            raise RuntimeError("No exports available on GCS")

        # parse the index name out of the latest file name
        index_name = self._get_index_name(latest.name)
        logger.info("Ensuring index exists", extra={"index": index_name})

        if self._create_index(index_name):
            logger.info("Start indexing", extra={"index": index_name})
            reporter = ProgressReporter(
                logger, "Indexing", latest.name, index_name, total_docs
            )
            indexed = 0
            gcs_stream = self.file_manager.stream_from_gcs(latest)
            for (operator, document) in stream_bulk(gcs_stream):
                op = json.loads(operator)
                doc = json.loads(document)
                categories: set[str] = set(doc.get("category", []))

                if not self._should_filter(categories):
                    self._enqueue(index_name, (op, doc))
                    indexed += self._index_docs(False)

                # report percent completed
                reporter.report(indexed)

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

    def _should_filter(self, categories: set[str]) -> bool:
        """Return True if we do not want to index this document."""
        # Takes the intersection of the categories and blocklist.
        # If there exists some shared categories with the blocklist,
        # then skip processing this document.
        overlapping_categories = categories & self.blocklist
        return overlapping_categories != set()

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
                if "errors" in res and res["errors"]:
                    raise Exception(res["errors"])
            except Exception as e:
                raise e
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
        settings = get_settings_for_version(self.index_version)
        if not exists and settings:
            res = indices_client.create(
                index=index_name,
                mappings=settings.SUGGEST_MAPPING,
                settings=settings.SUGGEST_SETTINGS,
            )
            return bool(res.get("acknowledged", False))

        return False

    def _flip_alias_to_latest(self, current_index: str, alias: str):
        alias = alias.format(version=self.index_version)

        # fetch previous index using alias so we know what to delete
        actions: list[Mapping[str, Any]] = [
            {"add": {"index": current_index, "alias": alias}}
        ]

        if self.es_client.indices.exists_alias(name=alias):
            indices = self.es_client.indices.get_alias(name=alias)
            for idx in indices:
                logger.info(
                    "adding index to be removed from alias",
                    extra={"index": idx, "alias": alias},
                )
                actions.append({"remove": {"index": idx, "alias": alias}})

        self.es_client.indices.update_aliases(actions=actions)
