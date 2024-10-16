"""Chunked remote settings uploader"""

import io
import json
import logging

from merino.jobs.utils.chunked_rs_uploader import Chunk, ChunkedRemoteSettingsUploader

logger = logging.getLogger(__name__)


class ChunkedRemoteSettingsRelevancyUploader(ChunkedRemoteSettingsUploader):
    """A class that uploads relevancy data to remote settings."""

    category: str

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
        allow_delete: bool = True,
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
            allow_delete,
            dry_run,
            total_item_count,
        )
        self.category_name = category_name
        self.category_code = category_code
        self.version = version

    def delete_records(self) -> None:
        """Delete records whose "category_code" is equal to the uploader's
        `category_code`.
        """
        logger.info(f"Deleting records with type: {self.record_type}")
        count = 0
        for record in self.kinto.get_records():
            record_details = record.get("record_custom_details", {})
            cat_to_domains_details = record_details.get("category_to_domains", {})
            if cat_to_domains_details.get("version") == self.version:
                logger.info(f"Deleting record: {record['id']}")
                if not self.dry_run:
                    self.kinto.delete_record(id=record["id"])
                    count += 1
        logger.info(f"Deleted {count} records")

    def _upload_chunk(self, chunk: Chunk) -> None:
        """Create a record and attachment for a chunk."""
        # The record ID will be "{record_type}-{start}-{end}", where `start` and
        # `end` are zero-padded based on the total suggestion count.
        places = 0 if not self.total_item_count else len(str(self.total_item_count))
        start = f"{chunk.start_index:0{places}}"
        end = f"{chunk.start_index + chunk.size:0{places}}"
        record_id = "-".join([self.category_name, start, end])
        record = {
            "id": record_id,
            "type": self.record_type,
            "record_custom_details": {
                "category_to_domains": {
                    "category": self.category_name.lower(),
                    "category_code": self.category_code,
                    "version": self.version,
                }
            },
        }
        attachment_json = json.dumps(chunk.to_json_serializable())

        logger.info(f"Uploading record: {record}")
        if not self.dry_run:
            self.kinto.update_record(data=record)

        logger.info(f"Uploading attachment json with {chunk.size} suggestions")
        logger.debug(attachment_json)
        if not self.dry_run:
            self.kinto.session.request(
                "post",
                f"/buckets/{self.kinto.bucket_name}/collections/"
                f"{self.kinto.collection_name}/records/{record_id}/attachment",
                files={
                    "attachment": (
                        f"{record_id}.json",
                        io.StringIO(attachment_json),
                        "application/json",
                    )
                },
            )
