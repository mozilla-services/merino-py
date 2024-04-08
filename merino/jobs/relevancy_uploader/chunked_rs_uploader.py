"""Chunked remote settings uploader"""
import io
import json
import logging
from typing import Any

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
        dry_run: bool = False,
        suggestion_score_fallback: float | None = None,
        total_data_count: int | None = None,
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
            suggestion_score_fallback,
            total_data_count,
        )
        self.category_name = category_name
        self.category_code = category_code

    def add_relevancy_data(self, data: Any) -> None:
        """Add Relevancy data to the current chunk."""
        self.current_chunk.add_data(data)
        if self.current_chunk.size == self.chunk_size:
            self._finish_current_chunk()

    def _finish_current_chunk(self) -> None:
        """If the current chunk is not empty, upload it and create a new empty
        current chunk.
        """
        self._upload_chunk(self.current_chunk)
        self.current_chunk = Chunk(
            self.current_chunk.start_index + self.current_chunk.size
        )

    def _upload_chunk(self, chunk: Chunk) -> None:
        """Create a record and attachment for a chunk."""
        # The record ID will be "{record_type}-{start}-{end}", where `start` and
        # `end` are zero-padded based on the total suggestion count.
        places = 0 if not self.total_data_count else len(str(self.total_data_count))
        start = f"{chunk.start_index:0{places}}"
        end = f"{chunk.start_index + chunk.size:0{places}}"
        record_id = "-".join([self.category_name, start, end])
        record = {
            "id": record_id,
            "type": self.record_type,
            "record_custom_details": {
                "category_to_domains": {
                    "category": self.category_name,
                    "category_code": self.category_code,
                }
            },
        }
        attachment_json = json.dumps(chunk.data)

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
