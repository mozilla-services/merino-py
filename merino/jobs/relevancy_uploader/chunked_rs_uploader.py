"""Chunked remote settings uploader"""

import logging
from typing import Any

from merino.jobs.utils.chunked_rs_uploader import Chunk, ChunkedRemoteSettingsUploader

logger = logging.getLogger(__name__)


class RelevancyChunk(Chunk):
    """A chunk of items for the relevancy uploader."""

    uploader: "ChunkedRemoteSettingsRelevancyUploader"

    def to_record(self) -> dict[str, Any]:
        """Create a record and attachment for a chunk."""
        start, end = self.pretty_indexes()
        record_id = "-".join([self.uploader.category_name, start, end])
        return {
            "id": record_id,
            "type": self.uploader.record_type,
            "record_custom_details": {
                "category_to_domains": {
                    "category": self.uploader.category_name.lower(),
                    "category_code": self.uploader.category_code,
                    "version": self.uploader.version,
                }
            },
        }


class ChunkedRemoteSettingsRelevancyUploader(ChunkedRemoteSettingsUploader):
    """A class that uploads relevancy data to remote settings."""

    category_name: str
    category_code: int
    version: int

    def __init__(
        self,
        auth: str,
        bucket: str,
        chunk_size: int,
        collection: str,
        record_type: str,
        server: str,
        category_name: str,
        category_code: int,
        version: int,
        dry_run: bool = False,
        total_item_count: int | None = None,
    ):
        """Initialize the uploader."""
        super().__init__(
            auth,
            bucket,
            chunk_size,
            collection,
            record_type,
            server,
            dry_run,
            total_item_count,
            chunk_cls=RelevancyChunk,
        )
        self.category_name = category_name
        self.category_code = category_code
        self.version = version

    def delete_records(self) -> None:
        """Delete records whose "category_code" is equal to the uploader's
        `category_code`.
        """
        logger.info(f"Deleting records with type: {self.record_type}")
        deleted_records = self.uploader.delete_if(self._delete_if_predicate)
        count = len(deleted_records)
        logger.info(f"Deleted {count} records")

    def _delete_if_predicate(self, record: dict[str, Any]) -> bool:
        record_details = record.get("record_custom_details", {})
        cat_to_domains_details = record_details.get("category_to_domains", {})
        if cat_to_domains_details.get("version") == self.version:
            logger.info(f"Deleting record: {record['id']}")
            return True
        return False
