"""Remote settings uploader"""

import json
import logging
import os
from tempfile import TemporaryDirectory
from typing import Any, Callable

import kinto_http

logger = logging.getLogger(__name__)


class RemoteSettingsUploader:
    """A class that uploads records and attachments to remote settings."""

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
        self.kinto = kinto_http.Client(
            server_url=server, bucket=bucket, collection=collection, auth=auth, dry_mode=dry_run
        )

    def upload(self, record: dict[str, Any], attachment: Any) -> None:
        """Create or update a record and its attachment."""
        record_id = record["id"]
        logger.info(f"Uploading record: {record_id}")
        logger.debug(json.dumps(record) + " ")

        self.kinto.update_record(data=record)

        attachment_json = json.dumps(attachment)
        logger.debug(f"Uploading attachment: {record_id}")

        # The logger apparently formats the message even when no args are
        # passed, and if `attachment_json` is an object literal (as opposed to
        # an array literal), the curly braces must confuse it because it ends up
        # logging nothing at all. Adding a trailing space seems to prevent that.
        logger.debug(attachment_json + " ")

        # `kinto.add_attachment()` only takes a path to an actual file
        # unfortunately, so create a temporary one.
        with TemporaryDirectory() as tmp_dir_name:
            path = os.path.join(tmp_dir_name, f"{record_id}.json")
            with open(path, "w") as file:
                file.write(attachment_json)
            self.kinto.add_attachment(
                id=record["id"],
                filepath=path,
                mimetype="application/json",
            )

    def delete_if(self, predicate: Callable[[dict[str, Any]], bool]) -> list[dict[str, Any]]:
        """Delete records that match a predicate. The predicate function is
        passed each record and should return True if it should be deleted. The
        deleted records are returned.

        """
        deleted_records = []
        for record in self.kinto.get_records():
            if predicate(record):
                deleted_records.append(record)
                self.kinto.delete_record(id=record["id"])

        return deleted_records
