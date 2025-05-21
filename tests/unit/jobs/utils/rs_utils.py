# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

#XXXadw update test_chunked_rs_uploader.py etc.

"""Helpers for remote settings uploader tests."""

import json
from typing import Any

from requests_toolbelt.multipart.decoder import MultipartDecoder


SERVER_DATA = {
    "auth": "Bearer auth",
    "bucket": "test-bucket",
    "collection": "test-collection",
    "dry_run": False,
    "hostname": "remote-settings",
    "server": "http://remote-settings",
}


class Record:
    """Encapsulates data for a remote settings record that should be created by
    the uploader.
    """

    attachment: Any
    attachment_url: str
    data: dict[str, Any]
    url: str

    def __init__(
        self,
        data: dict[str, Any],
        attachment: Any,
        bucket: str = "test-bucket",
        collection: str = "test-collection",
#         server: str = "http://localhost",
        server: str = "http://remote-settings",
    ):
        self.data = data
        self.attachment = attachment
        self.url = f"{server}/buckets/{bucket}/collections/{collection}/records/{self.id}"
        self.attachment_url = f"{self.url}/attachment"
        print(f"****XXXadw Record.__init__ data={data} self.data={self.data} self.url={self.url}")

    @property
    def id(self) -> str:
        """The record's ID."""
        id: str = self.data["id"]
        return id

    @property
    def expected_record_request(self) -> dict[str, Any]:
        """A dict that describes the request that Kinto should receive when the
        uploader uploads a record.
        """
        return {
            "method": "PUT",
            "url": self.url,
            "data": self.data,
        }

    @property
    def expected_attachment_request(self) -> dict[str, Any]:
        """A dict that describes the request that Kinto should receive when the
        uploader uploads an attachment.
        """
        return {
            "method": "POST",
            "url": self.attachment_url,
            "attachment": self.attachment,
            "headers": {
                "Content-Disposition": f'form-data; name="attachment"; filename="{self.id}.json"',
                "Content-Type": "application/json",
            },
        }

    @property
    def expected_delete_request(self) -> dict[str, Any]:
        """A dict that describes the request that Kinto should receive when the
        uploader deletes a record.
        """
        return {
            "method": "DELETE",
            "url": self.url,
        }


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
    print("***XXXadw check_upload_requests " + str([r.method for r in actual_requests]))
    assert len(actual_requests) == 2 * len(records)
    for r in records:
        check_request(actual_requests.pop(0), r.expected_record_request)
        check_request(actual_requests.pop(0), r.expected_attachment_request)


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
    records: list[Record],
    bucket: str = SERVER_DATA["bucket"],
    collection: str = SERVER_DATA["collection"],
    server: str = SERVER_DATA["server"],
) -> None:
    # the URL that returns all records
    #XXXadw urljoin
    records_url = "/".join(
        [
            server,
            "buckets",
            bucket,
            "collections",
            collection,
            "records",
        ]
    )
    requests_mock.get(
        records_url,
        json={
            "data": [r.data for r in records],
        },
    )

    # per-record URLs
    for r in records:
        print(f"****XXXadw mock_responses r.url={r.url}")
        print(f"****XXXadw mock_responses r.attachment_url={r.attachment_url}")
        requests_mock.put(r.url, json={})
        requests_mock.post(r.attachment_url, json={})
        requests_mock.delete(r.url, json={"data": [{"deleted": True, "id": r.id}]})
