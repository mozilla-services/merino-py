"""Remote settings client"""

import hashlib
import json
import logging
import os
from tempfile import TemporaryDirectory
from typing import Any, Iterable

import kinto_http

from merino.jobs.utils import pretty_file_size


# Inline remote settings record data, or in other words, a `dict` representation
# of a record.
RecordData = dict[str, Any]


logger = logging.getLogger(__name__)


class RemoteSettingsClient:
    """A simple wrapper for the Kinto client."""

    dry_run: bool
    kinto: kinto_http.Client

    def __init__(
        self,
        auth: str,
        bucket: str,
        collection: str,
        server: str,
        dry_run: bool = False,
    ):
        """Initialize the client. `dry_run` only prevents mutable requests."""
        # Kinto takes a `dry_mode` option, but it prevents even immutable
        # requests like getting records and downloading attachments. Some jobs
        # depend on getting records and attachments before they make changes,
        # and using `dry_mode=True` would make their dry runs essentially do
        # nothing, so we don't use it.
        self.dry_run = dry_run
        self.kinto = kinto_http.Client(
            server_url=server, bucket=bucket, collection=collection, auth=auth
        )

    def upload(
        self,
        record: RecordData,
        attachment: Any,
        existing_record: RecordData | None = None,
        force_reupload: bool = False,
    ) -> None:
        """Create or update a record and its attachment. If `existing_record` is
        defined and its attachment hash is the same as `attachment`'s hash,
        nothing is actually uploaded unless `force-reupload` is `True`.

        """
        record_id = record["id"]
        attachment_json = json.dumps(attachment)
        attachment_bytes = attachment_json.encode(encoding="utf-8")

        if not force_reupload and existing_record:
            attachment_hash = existing_record.get("attachment", {}).get("hash")
            new_hash = hashlib.sha256(attachment_bytes).hexdigest()
            if attachment_hash == new_hash:
                logger.info(f"Record has not changed: {record_id}")
                return

        logger.info(f"Updating record: {record_id}")
        logger.debug(json.dumps(record) + " ")

        if not self.dry_run:
            self.kinto.update_record(data=record)

        attachment_size = pretty_file_size(len(attachment_bytes))
        logger.info(f"Uploading attachment: {record_id} ({attachment_size})")

        # The logger apparently formats the message even when no args are
        # passed, and if `attachment_json` is an object literal (as opposed to
        # an array literal), the curly braces must confuse it because it ends up
        # logging nothing at all. Adding a trailing space seems to prevent that.
        logger.debug(attachment_json + " ")

        if not self.dry_run:
            # `kinto.add_attachment()` only takes a path to an actual file
            # unfortunately, so create a temporary one.
            with TemporaryDirectory() as tmp_dir_name:
                path = os.path.join(tmp_dir_name, f"{record_id}.json")
                with open(path, "wb") as file:
                    file.write(attachment_bytes)
                self.kinto.add_attachment(
                    id=record["id"],
                    filepath=path,
                    mimetype="application/json",
                )

    def get_records(self) -> list[RecordData]:
        """Get all records."""
        logger.info("Getting all records")
        records: list[RecordData] = self.kinto.get_records()
        return records

    def delete_record(self, id: str) -> None:
        """Delete a record by its ID."""
        logger.info(f"Deleting record: {id}")
        if not self.dry_run:
            self.kinto.delete_record(id=id)

    def download_attachment(self, record: RecordData) -> Any:
        """Download and return a record's attachment."""
        with TemporaryDirectory() as tmp_dir_name:
            logger.info(f"Downloading attachment for record: {record.get('id')}")
            path = self.kinto.download_attachment(record, filepath=tmp_dir_name)
            with open(path, "r") as file:
                return json.load(file)


def filter_expression(countries: Iterable[str] = [], locales: Iterable[str] = []) -> str:
    """Build a jexl filter expression."""
    terms = []
    if countries:
        terms.append(f"env.country in [{_join_items(countries)}]")
    if locales:
        terms.append(f"env.locale in [{_join_items(locales)}]")
    return " && ".join(terms)


def filter_expression_dict(
    countries: Iterable[str] = [], locales: Iterable[str] = []
) -> dict[str, str]:
    """Return a dict containing a "filter_expression", or an empty dict if the
    filter expression is empty.

    """
    expr = filter_expression(countries=countries, locales=locales)
    if not expr:
        return {}
    return {"filter_expression": expr}


def _join_items(items: Iterable[str]) -> str:
    return ", ".join([f"'{i}'" for i in sorted(items)])
