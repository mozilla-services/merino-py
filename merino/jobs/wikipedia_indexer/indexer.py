"""Builds the elasticsearch index from the export file"""
import json
import logging
from typing import Any, Dict, List, Mapping, Optional, Tuple

from elasticsearch import Elasticsearch
from google.cloud.storage import Blob

from merino.jobs.wikipedia_indexer.filemanager import FileManager
from merino.jobs.wikipedia_indexer.settings import get_settings_for_version
from merino.jobs.wikipedia_indexer.suggestion import Builder

logger = logging.getLogger(__name__)

# Maximum queue length
MAX_LENGTH = 5000


class Indexer:
    """Index documents from wikimedia search exports into Elasticsearch"""

    QUEUE_MAX_LENGTH = 5000

    queue: List[Mapping[str, Any]] = []

    suggestion_builder: Builder
    export_file: Blob
    index_version: str
    file_manager: FileManager
    client: Elasticsearch

    def __init__(
        self, index_version: str, file_manager: FileManager, client: Elasticsearch
    ):

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
        print(latest.name)
        index_name = self._get_index_name(latest.name)
        logger.info("Ensuring index exists", extra={"index": index_name})

        # TODO add configuration of optional indexing strategies
        if self._ensure_index(index_name)["acknowledged"]:
            prior: Optional[Mapping[str, Any]] = None
            logger.info("Start indexing", extra={"index": index_name})
            for i, line in enumerate(self.file_manager._stream_from_gcs(latest)):
                doc = json.loads(line)
                if prior and (i + 1) % 2 == 0:
                    self._enqueue(index_name, (prior, doc))
                    self._index_docs(False)
                    prior = None
                else:
                    prior = doc
                perc_done = round((i / 2) / total_docs * 100, 5)
                if perc_done > 1 and perc_done % 2 == 0:
                    logger.info(
                        "Indexing progress: {}%".format(perc_done),
                        extra={
                            "source": latest.name,
                            "index": index_name,
                            "percent_complete": perc_done,
                            "completed": i,
                            "total_size": total_docs,
                        },
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
            raise Exception("could not create the index")

    def _enqueue(self, index_name: str, tpl: Tuple[Mapping[str, Any], ...]):
        op, doc = self._parse_tuple(index_name, tpl)
        self.queue.append(op)
        self.queue.append(doc)

    def _index_docs(self, force: bool):
        qlen = len(self.queue)
        if qlen > 0 and (qlen >= self.QUEUE_MAX_LENGTH or force is True):
            res = None
            try:
                res = self.es_client.bulk(operations=self.queue)
                if res["errors"] is not False:
                    raise Exception(res["errors"])
            except Exception as e:
                print(res)
                raise e
            self.queue.clear()

    def _parse_tuple(
        self, index_name: str, tpl: Tuple[Mapping[str, Any], ...]
    ) -> Tuple[Dict[str, Any], ...]:
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
            file_name = file_name.split("/")[-1]
        base_name = "-".join(file_name.split("-")[:2])
        return f"{base_name}-{self.index_version}"

    def _ensure_index(self, index_name: str):
        indices_client = self.es_client.indices
        exists = indices_client.exists(index=index_name)
        settings = get_settings_for_version(self.index_version)
        if not exists and settings:
            return indices_client.create(
                index=index_name,
                mappings=settings.SUGGEST_MAPPING,
                settings=settings.SUGGEST_SETTINGS,
            )
        return {"acknowledged": True}

    def _flip_alias_to_latest(self, current_index: str, alias: str):
        # fetch previous index using alias so we know what to delete
        actions: List[Mapping[str, Any]] = [
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
