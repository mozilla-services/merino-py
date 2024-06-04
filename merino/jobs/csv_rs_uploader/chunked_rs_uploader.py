"""Chunked remote settings uploader"""
import logging
from typing import Any

import kinto_http

from merino.jobs.utils.chunked_rs_uploader import Chunk, ChunkedRemoteSettingsUploader

logger = logging.getLogger(__name__)


class ChunkedRemoteSettingsSuggestionUploader(ChunkedRemoteSettingsUploader):
    """A class that uploads suggestion data to remote settings.
    Data is uploaded and stored in chunks. Chunking is handled
    automatically, and the caller only needs to specify a chunk size and call
    `add_data()` until all data has been added:

        with ChunkedRemoteSettingsSuggestionUploader(
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

    The record's attachment will be the list of suggestions in the chunk as JSON
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
    suggestion_score_fallback: float | None
    total_data_count: int | None

    def __init__(
        self,
        auth: str,
        bucket: str,
        chunk_size: int,
        collection: str,
        record_type: str,
        server: str,
        dry_run: bool = False,
        suggestion_score_fallback: float | None = None,
        total_data_count: int | None = None,
    ):
        """Initialize the uploader."""
        super(ChunkedRemoteSettingsSuggestionUploader, self).__init__(
            auth,
            bucket,
            chunk_size,
            collection,
            record_type,
            server,
            dry_run,
            total_data_count,
        )
        self.suggestion_score_fallback = suggestion_score_fallback
        self.total_data_count = total_data_count

    def add_suggestion(self, suggestion: dict[str, Any]) -> None:
        """Add a suggestion. If the current chunk becomes full as a result, it
        will be uploaded before this method returns.
        """
        if self.suggestion_score_fallback and "score" not in suggestion:
            suggestion |= {"score": self.suggestion_score_fallback}
        self.current_chunk.add_data(suggestion)
        if self.current_chunk.size == self.chunk_size:
            self._finish_current_chunk()
