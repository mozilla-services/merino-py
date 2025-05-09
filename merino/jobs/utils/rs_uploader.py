"""Remote settings uploader"""

import io
import json
import logging
from typing import Any

import kinto_http

logger = logging.getLogger(__name__)


class RemoteSettingsUploader:
    #XXXadw fix comment
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

    kinto: kinto_http.Client

    def __init__(
        self,
        auth: str,
        bucket: str,
        collection: str,
        server: str,
        dry_run: bool = False,
    ):
        """Initialize the uploader."""
        if dry_run:
            self.kinto = None
        else:
            self.kinto = kinto_http.Client(
                server_url=server, bucket=bucket, collection=collection, auth=auth
            )

    def upload(self, record: dict[str, Any], attachment_json: str) -> None:
        """Create or update a record and its attachment."""
        record_id = record["id"]
        logger.info(f"Uploading record: {record_id}")
        if self.kinto:
            self.kinto.update_record(data=record)

        # The logger apparently formats the message even when no args are
        # passed, and if `attachment_json` is an object literal (as opposed to
        # an array literal), the curly braces must confuse it because it ends up
        # logging nothing at all. Adding a trailing space seems to prevent that.
        logger.info(f"Uploading attachment json")
        logger.debug(attachment_json + " ")

        if self.kinto:
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

    def delete(self, record_id: str) -> None:
        """Delete a record."""
        logger.info(f"Deleting record: {record_id}")
        if self.kinto:
            self.kinto.delete_record(id=record_id)
