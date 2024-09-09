"""Chunked remote settings uploader"""

import io
import json
import logging
from dataclasses import dataclass
from typing import Any

import kinto_http

logger = logging.getLogger(__name__)


class Chunk:
    """A chunk of suggestions to be uploaded in a single attachment."""

    start_index: int
    data: list[dict[str, Any]]

    def __init__(self, start_index: int):
        self.start_index = start_index
        self.data = []

    def add_data(self, data: dict[str, Any]) -> None:
        """Add data to the chunk."""
        self.data.append(data)

    @property
    def size(self) -> int:
        """Return the length of the data."""
        return len(self.data)


@dataclass
class KintoRecordUpdate:
    """Represents a Kinto update we want to perform"""

    record_data: Any
    attachment_json: str
    chunk_size: int


class DeletionNotAllowed(Exception):
    """Attempt to delete a record without the --allow-delete flag present"""

    pass


class ChunkedRemoteSettingsUploader:
    """A class that uploads data (e.g. suggestions of relevancy inputs) to remote
    settings. Data is uploaded and stored in chunks. Chunking is handled
    automatically, and the caller only needs to specify a chunk size and call
    `add_data()` until all data has been added:

        with ChunkedRemoteSettingsUploader(
            chunk_size=200,
            record_type="my-record-type",
            auth="my-auth",
            bucket="my-bucket",
            collection="my-collection",
            server="http://example.com/",
            total_suggestion_count=1234
        ) as uploader:
            for s in my_data:
                uploader.add_data(s)

    This class can be used with any type of data regardless of schema. The
    values passed to `add_data()` are dictionaries that can contain
    anything. However, the dictionaries must be JSON serializable, i.e., they
    must be able to be passed to `json.dumps()`. It's the consumer's
    responsibility to convert unserializable dicts to serializable dicts before
    passing them to the uploader.

    For each chunk, the uploader will create a record with an attachment. The
    record represents the chunk and the attachment contains the chunk's
    data as JSON. All chunks will contain the number of data
    specified by the uploader's `chunk_size` except possibly the final chunk,
    which may contain fewer suggestions.

    Each record's "id" will encode the uploader's `record_type` and the range of
    data contained in the record's chunk, and its "type" will be the
    uploader's `record_type`, like this:

        {
            "id": f"{uploader.record_type}-{chunk.start_index}-{chunk.start_index + chunk.size}",
            "type": uploader.record_type
        }

    For example, if the uploader's `record_type` is "my-record-type", then the
    record for a chunk with start index 400 and size 200 will look like this:

        { "id": "my-record-type-400-600", "type": "my-record-type" }

    The record's attachment will be the list of data in the chunk as JSON
    (MIME type "application/json").

    It's common to delete existing suggestions before uploading new ones, so as
    a convenience the uploader can also delete all records of its `record_type`:

        uploader.delete_records()

    """

    chunk_size: int
    current_chunk: Chunk
    dry_run: bool
    kinto: kinto_http.Client
    record_type: str
    total_data_count: int | None
    # Records to add/update/delete in Kinto.  Keyed by record ID.  None indicates deletion.
    _kinto_changes: dict[str, KintoRecordUpdate | None]

    def __init__(
        self,
        auth: str,
        bucket: str,
        chunk_size: int,
        collection: str,
        record_type: str,
        server: str,
        allow_delete: bool = False,
        dry_run: bool = False,
        total_data_count: int | None = None,
    ):
        """Initialize the uploader."""
        self.chunk_size = chunk_size
        self.current_chunk = Chunk(0)
        self.allow_delete = allow_delete
        self.dry_run = dry_run
        self.record_type = record_type
        self.total_data_count = total_data_count
        self.kinto = kinto_http.Client(
            server_url=server, bucket=bucket, collection=collection, auth=auth
        )
        self._kinto_changes = {}

    def add_data(self, data: dict[str, Any]) -> None:
        """Add data to the current_chunk. If the current chunk becomes full as a result, it
        will be uploaded before this method returns.
        """
        self.current_chunk.add_data(data)
        if self.current_chunk.size == self.chunk_size:
            self._finish_current_chunk()

    def finish(self) -> None:
        """Finish the currrent chunk. If the chunk is not empty, it will be
        uploaded before this method returns. This method should be called when
        the caller is done with the uploader. If the uploader was created in a
        `with` statement (as a context manager), this is called automatically.
        """
        self._finish_current_chunk()

    def _execute_kinto_changes(self):
        records_to_delete = [
            record_id for (record_id, change) in self._kinto_changes.items() if change is None
        ]
        records_to_update = [
            (record_id, change)
            for (record_id, change) in self._kinto_changes.items()
            if change is not None
        ]

        if not self.allow_delete and records_to_delete:
            id_list = ", ".join(records_to_delete)
            raise DeletionNotAllowed(f"Attempt to delete records: {id_list}")

        for record_id in records_to_delete:
            logger.info(f"Deleting record: {record_id}")
            if not self.dry_run:
                self.kinto.delete_record(id=record_id)

        for record_id, change in records_to_update:
            logger.info(f"Uploading record: {record_id}")
            if not self.dry_run:
                self.kinto.update_record(data=change.record_data)

            logger.info(f"Uploading attachment json with {change.chunk_size} suggestions")
            logger.debug(change.attachment_json)
            if not self.dry_run:
                self.kinto.session.request(
                    "post",
                    f"/buckets/{self.kinto.bucket_name}/collections/"
                    f"{self.kinto.collection_name}/records/{record_id}/attachment",
                    files={
                        "attachment": (
                            f"{record_id}.json",
                            io.StringIO(change.attachment_json),
                            "application/json",
                        )
                    },
                )

        if len(records_to_delete) > 0:
            logger.info(f"Deleted {len(records_to_delete)} records")

        if len(records_to_update) > 0:
            logger.info(f"Updated {len(records_to_update)} records")
        self._kinto_changes = {}

    def delete_records(self) -> None:
        """Delete records whose "type" is equal to the uploader's
        `record_type`.
        """
        logger.info(f"Deleting records with type: {self.record_type}")
        for record in self.kinto.get_records():
            if record.get("type") == self.record_type:
                self._kinto_changes[record["id"]] = None

    def _finish_current_chunk(self) -> None:
        """If the current chunk is not empty, upload it and create a new empty
        current chunk.
        """
        if self.current_chunk.size:
            self._upload_chunk(self.current_chunk)
            self.current_chunk = Chunk(self.current_chunk.start_index + self.current_chunk.size)

    def _upload_chunk(self, chunk: Chunk) -> None:
        """Create a record and attachment for a chunk."""
        # The record ID will be "{record_type}-{start}-{end}", where `start` and
        # `end` are zero-padded based on the total suggestion count.
        places = 0 if not self.total_data_count else len(str(self.total_data_count))
        start = f"{chunk.start_index:0{places}}"
        end = f"{chunk.start_index + chunk.size:0{places}}"
        record_id = "-".join([self.record_type, start, end])
        record = {
            "id": record_id,
            "type": self.record_type,
        }
        attachment_json = json.dumps(chunk.data)

        self._kinto_changes[record_id] = KintoRecordUpdate(
            record_data=record,
            chunk_size=chunk.size,
            attachment_json=attachment_json,
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.finish()
        self._execute_kinto_changes()
