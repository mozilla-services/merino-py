# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for relevancy_uploader.chunked_rs_uploader.py."""

import json
from typing import Any

from requests_toolbelt.multipart.decoder import MultipartDecoder

from merino.jobs.relevancy_uploader import ChunkedRemoteSettingsRelevancyUploader

TEST_UPLOADER_KWARGS: dict[str, Any] = {
    "auth": "Bearer auth",
    "bucket": "test-bucket",
    "collection": "test-collection",
    "record_type": "science",
    "server": "http://localhost",
    "category_name": "science",
    "category_code": 1,
}


class Record:
    """Encapsulates data for a remote settings record that should be created by
    the chunked uploader.
    """

    attachment_url: str
    id: str
    type: str
    start_index: int
    size: int
    url: str

    def __init__(
        self,
        start_index: int,
        size: int,
        bucket: str = TEST_UPLOADER_KWARGS["bucket"],
        collection: str = TEST_UPLOADER_KWARGS["collection"],
        server: str = TEST_UPLOADER_KWARGS["server"],
        type: str = TEST_UPLOADER_KWARGS["record_type"],
        id: str | None = None,
    ):
        self.start_index = start_index
        self.size = size
        self.type = type
        self.id = id or f"{type}-{start_index}-{size}"
        self.url = (
            f"{server}/buckets/{bucket}/collections/{collection}/records/{self.id}"
        )
        self.attachment_url = f"{self.url}/attachment"

    @property
    def expected_record_request(self) -> dict[str, Any]:
        """A dict that describes the request that Kinto should receive when the
        uploader uploads a record.
        """
        return {
            "method": "PUT",
            "url": self.url,
            "data": {
                "id": self.id,
                "type": self.type,
                "record_custom_details": {
                    "category_to_domains": {
                        "category": self.type,
                        "category_code": 1,
                    }
                },
            },
        }

    @property
    def expected_attachment_request(self) -> dict[str, Any]:
        """A dict that describes the request that Kinto should receive when the
        uploader uploads an attachment.
        """
        attachment: list[dict[str, Any]] = [
            {"i": i} for i in range(self.start_index, self.size)
        ]

        return {
            "method": "POST",
            "url": self.attachment_url,
            "attachment": attachment,
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

    @property
    def data(self) -> dict[str, Any]:
        """A dict that describes the data object that Kinto should return for
        the record.
        """
        return {
            "id": self.id,
            "type": self.type,
            "record_custom_details": {
                "category_to_domains": {
                    "category": self.type,
                    "category_code": 1,
                }
            },
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


def check_upload_requests(
    actual_requests: list, expected_records: list[Record]
) -> None:
    """Assert a list of actual requests matches expected requests given the
    expected records. Each record should correspond to two requests, one for
    uploading the record and one for uploading the attachment.
    """
    assert len(actual_requests) == 2 * len(expected_records)
    for r in expected_records:
        check_request(actual_requests.pop(0), r.expected_record_request)
        check_request(actual_requests.pop(0), r.expected_attachment_request)


def do_upload_test(
    requests_mock,
    chunk_size: int,
    data_count: int,
    expected_records: list[Record],
    uploader_kwargs: dict[str, Any] = {},
) -> None:
    """Perform an upload test."""
    for record in expected_records:
        requests_mock.put(record.url, json={})  # nosec
        requests_mock.post(record.attachment_url, json={})  # nosec

    with ChunkedRemoteSettingsRelevancyUploader(
        chunk_size=chunk_size,
        version=1,
        **TEST_UPLOADER_KWARGS,
        **uploader_kwargs,
    ) as uploader:
        for i in range(data_count):
            data: dict[str, Any] = {"i": i}
            uploader.add_relevancy_data(data)

    check_upload_requests(requests_mock.request_history, expected_records)


def test_dry_run(requests_mock):
    """Tests a dry run."""
    do_upload_test(
        requests_mock,
        chunk_size=10,
        data_count=100,
        uploader_kwargs={
            "dry_run": True,
        },
        expected_records=[],
    )
