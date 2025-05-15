"""Chunked remote settings uploader"""

import logging
from typing import Any, Tuple

from merino.jobs.utils.rs_uploader import RemoteSettingsUploader

logger = logging.getLogger(__name__)


class Chunk:
    """A chunk of items to be uploaded in a single attachment. Can be subclassed
    to support specialized chunk types and handling.

    """

    uploader: "ChunkedRemoteSettingsUploader"
    start_index: int
    items: list[Any]

    @staticmethod
    def item_to_json_serializable(item: Any) -> Any:
        """Convert the item to a JSON serializable object."""
        return item

    def __init__(self, uploader: "ChunkedRemoteSettingsUploader", start_index: int):
        self.uploader = uploader
        self.start_index = start_index
        self.items = []

    @property
    def size(self) -> int:
        """Return the number of items in the chunk."""
        return len(self.items)

    def add_item(self, item: Any) -> None:
        """Add an item to the chunk."""
        self.items.append(item)

    def to_record(self) -> dict[str, Any]:
        """Create the record for the chunk. Subclasses can override this to
        return a different record.

        """
        start, end = self.pretty_indexes()
        record_id = "-".join([self.uploader.record_type, start, end])
        return {
            "id": record_id,
            "type": self.uploader.record_type,
        }

    def to_attachment(self) -> Any:
        """Create the attachment for the chunk. Subclasses can override this to
        return a different attachment.

        """
        return [self.item_to_json_serializable(i) for i in self.items]

    def pretty_indexes(self) -> Tuple[str, str]:
        """Return (start, end) where `start` and `end` are the start and end
        indexes of this chunk as zero-padded strings based on the total
        suggestion count.

        """
        places = (
            0 if not self.uploader.total_item_count else len(str(self.uploader.total_item_count))
        )
        start = f"{self.start_index:0{places}}"
        end = f"{self.start_index + self.size:0{places}}"
        return (start, end)


class ChunkedRemoteSettingsUploader:
    """A class that uploads items to remote settings. Items are uploaded and
    stored in chunks. Chunking is handled automatically, and the caller only
    needs to specify a chunk size and call `add_item()` until all items have
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
        self.current_chunk = chunk_cls(self, 0)
        self.record_type = record_type
        self.total_item_count = total_item_count
        self.uploader = RemoteSettingsUploader(
            auth=auth,
            bucket=bucket,
            collection=collection,
            server=server,
            dry_run=dry_run,
        )

    def add_item(self, item: dict[str, Any]) -> None:
        """Add an item to the current_chunk. If the chunk becomes full as a
        result, it will be uploaded before this method returns.

        """
        self.current_chunk.add_item(item)
        if self.current_chunk.size == self.chunk_size:
            self._finish_current_chunk()

    def finish(self) -> None:
        """Finish the currrent chunk. If the chunk is not empty, it will be
        uploaded before this method returns. This method should be called when
        the caller is done with the uploader. If the uploader was created in a
        `with` statement (as a context manager), this is called automatically.
        """
        self._finish_current_chunk()

    def delete_records(self) -> None:
        """Delete records whose "type" is equal to the uploader's
        `record_type`.
        """
        logger.info(f"Deleting records with type: {self.record_type}")
        self.uploader.delete_if(lambda record: record.get("type") == self.record_type)

    def _finish_current_chunk(self) -> None:
        """If the current chunk is not empty, upload it and create a new empty
        current chunk.
        """
        if self.current_chunk.size:
            self._upload_chunk(self.current_chunk)
            self.current_chunk = self.chunk_cls(
                self, self.current_chunk.start_index + self.current_chunk.size
            )

    def _upload_chunk(self, chunk: Chunk) -> None:
        """Create a record and attachment for a chunk."""
        self.uploader.upload(
            record=chunk.to_record(),
            attachment=chunk.to_attachment(),
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.finish()
