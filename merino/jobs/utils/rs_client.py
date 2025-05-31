"""Remote settings client"""

import json
import logging
import os
from tempfile import TemporaryDirectory
from typing import Any

import kinto_http

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

    def upload(self, record: dict[str, Any], attachment: Any) -> None:
        """Create or update a record and its attachment."""
        record_id = record["id"]
        logger.info(f"Uploading record: {record_id}")
        logger.debug(json.dumps(record) + " ")

        if not self.dry_run:
            self.kinto.update_record(data=record)

        attachment_json = json.dumps(attachment)
        logger.debug(f"Uploading attachment: {record_id}")

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
                with open(path, "w") as file:
                    file.write(attachment_json)
                self.kinto.add_attachment(
                    id=record["id"],
                    filepath=path,
                    mimetype="application/json",
                )

    def get_records(self) -> list[dict[str, Any]]:
        """Get all records."""
        records: list[dict[str, Any]] = self.kinto.get_records()
        return records

    def delete_record(self, id: str) -> None:
        """Delete a record by its ID."""
        if not self.dry_run:
            self.kinto.delete_record(id=id)

    def download_attachment(self, record: dict[str, Any]) -> Any:
        """Download and return a record's attachment."""
        path = self.kinto.download_attachment(record)
        with open(path, "r") as file:
            return json.load(file)


def filter_expression(countries: list[str] = [], locales: list[str] = []) -> str:
    """Build a jexl filter expression."""
    terms = []
    if countries:
        terms.append(f"env.country in [{_join_items(countries)}]")
    if locales:
        terms.append(f"env.locale in [{_join_items(locales)}]")
    return " && ".join(terms)


def filter_expression_dict(countries: list[str] = [], locales: list[str] = []) -> dict[str, str]:
    """Return a dict containing a "filter_expression", or an empty dict if the
    filter expression is empty.

    """
    expr = filter_expression(countries=countries, locales=locales)
    if not expr:
        return {}
    return {"filter_expression": expr}


def _join_items(items: list[str]) -> str:
    return ", ".join([f"'{i}'" for i in sorted(items)])
