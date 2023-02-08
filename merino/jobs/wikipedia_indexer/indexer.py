"""Builds the elasticsearch index from the export file"""
import json
import logging
from typing import Any, Mapping, Optional

from elasticsearch import Elasticsearch
from google.cloud.storage import Blob

from merino.jobs.wikipedia_indexer.filemanager import FileManager
from merino.jobs.wikipedia_indexer.settings import get_settings_for_version
from merino.jobs.wikipedia_indexer.suggestion import Builder

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

    def __init__(
        self, index_version: str, file_manager: FileManager, client: Elasticsearch
    ):
        self.queue = []
        self.index_version = index_version
        self.file_manager = file_manager
        self.es_client = client
        self.suggestion_builder = Builder(index_version)

    def index_from_export(self, total_docs: int, elasticsearch_alias: str):
        """Primary indexer method.
        Reads the export file directly from GCS, indexes and swaps index aliases
        """
        logger.info("Ensuring latest dump is on GCS")
        latest = self.file_manager.get_latest_gcs()
        if not latest.name:
            raise RuntimeError("No exports available on gcs")

        # parse the index name out of the latest file name
        index_name = self._get_index_name(latest.name)
        logger.info("Ensuring index exists", extra={"index": index_name})

        if self._ensure_index(index_name):
            prior: Optional[Mapping[str, Any]] = None
            logger.info("Start indexing", extra={"index": index_name})
            indexed, perc_done = 0, 0.0
            for i, line in enumerate(self.file_manager._stream_from_gcs(latest)):
                doc = json.loads(line)
                if prior and (i + 1) % 2 == 0:
                    self._enqueue(index_name, (prior, doc))
                    indexed += self._index_docs(False)
                    prior = None
                else:
                    prior = doc

                # report percent completed
                perc_done = self._report_completed(
                    perc_done, latest.name, index_name, indexed, total_docs
                )

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

    def _report_completed(
        self,
        last_perc: float,
        source: str,
        dest: str,
        completed: int,
        total: int,
    ) -> float:
        perc_done = round(completed / total * 100, 5)
        if last_perc != perc_done and perc_done > 1 and perc_done % 1 == 0:
            logger.info(
                f"Indexing progress: {perc_done}%",
                extra={
                    "source": source,
                    "destination": dest,
                    "percent_complete": perc_done,
                    "completed": completed,
                    "total_size": total,
                },
            )
            return perc_done
        return last_perc

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
        if "/" in file_name:
            _, file_name = file_name.rsplit("/", 1)
        base_name = "-".join(file_name.split("-")[:2])
        return f"{base_name}-{self.index_version}"

    def _ensure_index(self, index_name: str) -> bool:
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

        return bool(exists)

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
