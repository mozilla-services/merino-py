# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Helpers for remote settings uploader tests."""

import hashlib
import json
from typing import Any
from urllib.parse import urljoin

from requests_toolbelt.multipart.decoder import MultipartDecoder

from merino.jobs.utils.rs_client import RecordData


SERVER_DATA = {
    "auth": "Bearer auth",
    "bucket": "test-bucket",
    "collection": "test-collection",
    "server": "http://remote-settings",
}


class Record:
    """An RS record and its attachment."""

    attachment: Any
    bucket: str
    collection: str
    data: RecordData
    post_attachment_url: str
    url: str

    def __init__(
        self,
        data: RecordData,
        attachment: Any,
        bucket: str = SERVER_DATA["bucket"],
        collection: str = SERVER_DATA["collection"],
        server: str = SERVER_DATA["server"],
    ):
        """Initialize the record. `data` is the record's inline data.
        `attachment` can be any JSON'able value.

        """
        self.data = data
        self.attachment = attachment
        self.bucket = bucket
        self.collection = collection
        self.url = f"{server}/buckets/{bucket}/collections/{collection}/records/{self.id}"
        self.post_attachment_url = f"{self.url}/attachment"

    @property
    def id(self) -> str:
        """The record's ID."""
        id: str = self.data["id"]
        return id

    @property
    def expected_record_request(self) -> dict[str, Any]:
        """A dict that describes the request that Kinto should receive when the
        record is uploaded.

        """
        return {
            "method": "PUT",
            "url": self.url,
            "data": self.data,
        }

    @property
    def expected_attachment_request(self) -> dict[str, Any]:
        """A dict that describes the request that Kinto should receive when the
        record's attachment is uploaded.

        """
        return {
            "method": "POST",
            "url": self.post_attachment_url,
            "attachment": self.attachment,
            "headers": {
                "Content-Disposition": f'form-data; name="attachment"; filename="{self.id}.json"',
                "Content-Type": "application/json",
            },
        }

    @property
    def expected_delete_request(self) -> dict[str, Any]:
        """A dict that describes the request that Kinto should receive when the
        record is deleted.

        """
        return {
            "method": "DELETE",
            "url": self.url,
        }

    def all_data(self) -> RecordData:
        """All the record's data, including its attachment metadata, that should
        be returned for the record by the RS server.

        """
        metadata = self.attachment_metadata()
        metadata_dict = {"attachment": metadata} if metadata else {}
        return self.data | metadata_dict

    def attachment_metadata(self) -> dict[str, Any] | None:
        """Attachment metadata dict."""
        if not self.attachment:
            return None
        filename = self.id
        json_bytes = json.dumps(self.attachment).encode(encoding="utf-8")
        return {
            "hash": hashlib.sha256(json_bytes).hexdigest(),
            "filename": filename,
            "mimetype": "application/json; charset=UTF-8",
            "size": len(json_bytes),
            "location": f"attachments/{self.bucket}/{self.collection}/{filename}",
        }

    def __repr__(self) -> str:
        return str(vars(self))


def check_request(actual, expected: dict[str, Any]) -> None:
    """Assert an actual request matches an expected request."""
    assert actual.url == expected["url"]
    assert actual.method == expected["method"]
    if "data" in expected:
        assert json.loads(actual.text) == {"data": expected["data"]}
    if "attachment" in expected:
        boundary = actual.text.split("\r\n")[0]
        mime = f'multipart/form-data; boundary="{boundary[2:]}"'
        decoder = MultipartDecoder(actual.body, mime)
        attachment = decoder.parts[0]
        assert json.loads(attachment.text) == expected["attachment"]
        if "headers" in expected:
            actual_headers = {
                name.decode(attachment.encoding): value.decode(attachment.encoding)
                for name, value in attachment.headers.items()
            }
            assert actual_headers == expected["headers"]


def check_upload_requests(actual_requests: list, records: list[Record]) -> None:
    """Assert a list of actual requests matches expected upload requests for
    some records. Each record should correspond to two requests, one for
    uploading the record and one for uploading the attachment.

    """
    upload_requests = [r for r in actual_requests if r.method in ["PUT", "POST"]]
    assert len(upload_requests) == 2 * len(records)
    for r in records:
        check_request(upload_requests.pop(0), r.expected_record_request)
        check_request(upload_requests.pop(0), r.expected_attachment_request)


def check_delete_requests(actual_requests: list, records: list[Record]) -> None:
    """Assert a list of actual requests matches expected delete requests for
    some records.

    """
    delete_requests = [r for r in actual_requests if r.method == "DELETE"]
    assert len(delete_requests) == len(records)
    for r in records:
        check_request(delete_requests.pop(0), r.expected_delete_request)


def mock_responses(
    requests_mock,
    get: list[Record] = [],
    update: list[Record] = [],
    delete: list[Record] = [],
    bucket: str = SERVER_DATA["bucket"],
    collection: str = SERVER_DATA["collection"],
    server: str = SERVER_DATA["server"],
) -> None:
    """Set up mock RS responses for the given records."""
    # get server capabilities
    requests_mock.get(
        server,
        json={
            "capabilities": {
                "attachments": {
                    "base_url": urljoin(server, "/"),
                },
            },
        },
    )

    # get all records
    records_url = urljoin(
        server,
        "/".join(
            [
                "buckets",
                bucket,
                "collections",
                collection,
                "records",
            ]
        ),
    )
    requests_mock.get(
        records_url,
        json={
            "data": [r.all_data() for r in get],
        },
    )

    for r in get:
        # get attachment
        attachment_metadata = r.all_data().get("attachment")
        if attachment_metadata:
            requests_mock.get(urljoin(server, attachment_metadata["location"]), json=r.attachment)

    for r in update:
        # update record
        requests_mock.put(r.url, json={})

        # post attachment
        requests_mock.post(r.post_attachment_url, json={})

    for r in delete:
        # delete record
        requests_mock.delete(r.url, json={"data": [{"deleted": True, "id": r.id}]})
