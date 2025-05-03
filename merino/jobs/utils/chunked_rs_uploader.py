"""Chunked remote settings uploader"""

import json
import logging
from dataclasses import dataclass
from typing import Any

from merino.jobs.utils.rs_uploader import RemoteSettingsUploader

logger = logging.getLogger(__name__)


class Chunk:
    """A chunk of items to be uploaded in a single attachment. Can be subclassed
    to support specialized chunk types and handling.

    """

    start_index: int
    items: list[Any]
    record_id: str | None = None

    @staticmethod
    def item_to_json_serializable(item: Any) -> Any:
        """Convert the item to a JSON serializable object."""
        return item

    def __init__(self, start_index: int):
        self.start_index = start_index
        self.items = []

    @property
    def size(self) -> int:
        """Return the number of items in the chunk."""
        return len(self.items)

    def add_item(self, item: Any) -> None:
        """Add an item to the chunk."""
        self.items.append(self.item_to_json_serializable(item))

    def to_json_serializable(self) -> Any:
        """Convert the chunk to a JSON serializable object that will be stored
        in the chunk's attachment.

        """
        return self.items


class ChunkedRemoteSettingsUploader:
    """A class that uploads items to remote settings. Items are uploaded and
    stored in chunks. Chunking is handled automatically, and the caller only
    needs to specify a chunk size and call `add_item()` until all items haveq
    been added:

        with ChunkedRemoteSettingsUploader(
            chunk_size=200,
            record_type="my-record-type",
            auth="my-auth",
            bucket="my-bucket",
            collection="my-collection",
            server="http://example.com/",
            total_suggestion_count=1234
        ) as uploader:
            for i in my_items:
                uploader.add_item(i)

    This class can be used with any type of data regardless of schema. The
    values passed to `add_item()` are dictionaries that can contain
    anything. However, the dictionaries must be JSON serializable, i.e., they
    must be able to be passed to `json.dumps()`. It's the consumer's
    responsibility to convert unserializable dicts to serializable dicts before
    passing them to the uploader.

    For each chunk, the uploader will create a record with an attachment. The
    record represents the chunk and the attachment contains the chunk's data as
    JSON. All chunks will contain the number of items specified by the
    uploader's `chunk_size` except possibly the final chunk, which may contain
    fewer items.

    Each record's "id" will encode the uploader's `record_type` and the range of
    items contained in the record's chunk, and its "type" will be the uploader's
    `record_type`, like this:

        {
            "id": f"{uploader.record_type}-{chunk.start_index}-{chunk.start_index + chunk.size}",
            "type": uploader.record_type
        }

    For example, if the uploader's `record_type` is "my-record-type", then the
    record for a chunk with start index 400 and size 200 will look like this:

        { "id": "my-record-type-400-600", "type": "my-record-type" }

    The record's attachment will be the list of items in the chunk as JSON (MIME
    type "application/json").

    It's common to delete existing suggestions before uploading new ones, so as
    a convenience the uploader can also delete all records of its `record_type`:

        uploader.delete_records()

    """

    chunk_cls: type[Chunk]
    chunk_size: int
    current_chunk: Chunk
    record_type: str
    total_item_count: int | None
    uploader: RemoteSettingsUploader
    staged_chunks: list[Chunk]
    staged_deleted_record_ids: list[str]

    def __init__(
        self,
        auth: str,
        bucket: str,
        chunk_size: int,
        collection: str,
        record_type: str,
        server: str,
        dry_run: bool = False,
        total_item_count: int | None = None,
        chunk_cls: type[Chunk] = Chunk,
    ):
        """Initialize the uploader."""
        self.chunk_cls = chunk_cls
        self.chunk_size = chunk_size
        self.current_chunk = chunk_cls(0)
        self.record_type = record_type
        self.total_item_count = total_item_count
        self.uploader = RemoteSettingsUploader(
            auth=auth,
            bucket=bucket,
            collection=collection,
            server=server,
            dry_run=dry_run,
        )
        self.staged_chunks = []
        self.staged_deleted_record_ids = []

    def add_item(self, item: dict[str, Any]) -> None:
        """Add an item to the current_chunk. If the chunk becomes full as a
        result, it will be uploaded before this method returns.

        """
        self.current_chunk.add_item(item)
        if self.current_chunk.size == self.chunk_size:
            self._stage_current_chunk()

    def finish(self) -> None:
        """Finish the currrent chunk. If the chunk is not empty, it will be
        uploaded before this method returns. This method should be called when
        the caller is done with the uploader. If the uploader was created in a
        `with` statement (as a context manager), this is called automatically.
        """
        self._stage_current_chunk()
        self._execute_kinto_changes()

    def _execute_kinto_changes(self):
        for record_id in self.staged_deleted_record_ids:
            self.uploader.delete(record_id)

        for chunk in self.staged_chunks:
            self.uploader.upload(
                record={
                    "id": chunk.record_id,
                    "type": self.record_type,
                },
                attachment_json=json.dumps(chunk.to_json_serializable()),
            )

        if len(self.staged_deleted_record_ids) > 0:
            logger.info(f"Deleted {len(self.staged_deleted_record_ids)} records")

        if len(self.staged_chunks) > 0:
            logger.info(f"Updated {len(self.staged_chunks)} records")

        self.staged_deleted_record_ids = []
        self.staged_chunks = []


    def delete_records(self) -> None:
        """Delete records whose "type" is equal to the uploader's
        `record_type`.
        """
        logger.info(f"Deleting records with type: {self.record_type}")
        if self.uploader.kinto:
            for record in self.uploader.kinto.get_records():
                if record.get("type") == self.record_type:
                    self.staged_deleted_record_ids.append(record["id"])

    def _stage_current_chunk(self) -> None:
        """If the current chunk is not empty, upload it and create a new empty
        current chunk.
        """
        chunk = self.current_chunk
        if chunk.size == 0:
            return

        # The record ID will be "{record_type}-{start}-{end}", where `start` and
        # `end` are zero-padded based on the total suggestion count.
        places = 0 if not self.total_item_count else len(str(self.total_item_count))
        start = f"{chunk.start_index:0{places}}"
        end = f"{chunk.start_index + chunk.size:0{places}}"
        record_id = "-".join([self.record_type, start, end])
        chunk.record_id = record_id
        self.staged_chunks.append(chunk)

        self.current_chunk = self.chunk_cls(
            self.current_chunk.start_index + self.current_chunk.size
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.finish()
