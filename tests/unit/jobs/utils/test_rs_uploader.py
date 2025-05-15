# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for rs_uploader.py."""

import json
from typing import Any, Callable

from requests_toolbelt.multipart.decoder import MultipartDecoder

from merino.jobs.utils.rs_uploader import RemoteSettingsUploader

TEST_UPLOADER_KWARGS: dict[str, Any] = {
    "auth": "Bearer auth",
    "bucket": "test-bucket",
    "collection": "test-collection",
    "dry_run": False,
    "server": "http://localhost",
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
        bucket: str = TEST_UPLOADER_KWARGS["bucket"],
        collection: str = TEST_UPLOADER_KWARGS["collection"],
        server: str = TEST_UPLOADER_KWARGS["server"],
    ):
        self.data = data
        self.attachment = attachment
        self.url = f"{server}/buckets/{bucket}/collections/{collection}/records/{self.id}"
        self.attachment_url = f"{self.url}/attachment"

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


def do_upload_test(
    requests_mock,
    records: list[Record],
    expected_records: list[Record] | None = None,
    uploader_kwargs: dict[str, Any] = {},
) -> None:
    """Perform an upload test."""
    for record in records:
        requests_mock.put(record.url, json={})  # nosec
        requests_mock.post(record.attachment_url, json={})  # nosec

    uploader = RemoteSettingsUploader(**(TEST_UPLOADER_KWARGS | uploader_kwargs))
    for record in records:
        uploader.upload(record=record.data, attachment=record.attachment)

    expected_records = expected_records if expected_records is not None else records
    check_upload_requests(requests_mock.request_history, expected_records)


def do_delete_if_test(
    requests_mock,
    predicate: Callable[[dict[str, Any]], bool],
    expected_deleted_records: list[Record],
    uploader_kwargs: dict[str, Any] = {},
) -> None:
    """Perform a delete_if test."""
    records = [
        Record(
            data={"id": "test-0"},
            attachment=["test-0-aaa", "test-0-bbb"],
        ),
        Record(
            data={"id": "test-1", "type": "test-type-aaa"},
            attachment=["test-1-aaa", "test-1-bbb"],
        ),
        Record(
            data={"id": "test-2", "type": "test-type-bbb"},
            attachment=["test-2-aaa", "test-2-bbb"],
        ),
        Record(
            data={"id": "test-3", "type": "test-type-aaa"},
            attachment=["test-3-aaa", "test-3-bbb"],
        ),
    ]

    records_url = "/".join(
        [
            TEST_UPLOADER_KWARGS["server"],
            "buckets",
            TEST_UPLOADER_KWARGS["bucket"],
            "collections",
            TEST_UPLOADER_KWARGS["collection"],
            "records",
        ]
    )
    requests_mock.get(
        records_url,
        json={
            "data": [r.data for r in records],
        },
    )

    for record in records:
        requests_mock.put(record.url, json={})  # nosec
        requests_mock.post(record.attachment_url, json={})  # nosec
        requests_mock.delete(record.url, json={"data": [{"deleted": True, "id": record.id}]})

    uploader = RemoteSettingsUploader(**(TEST_UPLOADER_KWARGS | uploader_kwargs))
    deleted_records = uploader.delete_if(predicate)
    assert deleted_records == [r.data for r in expected_deleted_records]

    check_delete_requests(requests_mock.request_history, expected_deleted_records)


def test_upload(requests_mock):
    """Basic upload test"""
    do_upload_test(
        requests_mock,
        records=[
            Record(
                data={"id": "test-0"},
                attachment={"foo": "bar"},
            ),
            Record(
                data={"id": "test-1", "type": "test-type"},
                attachment={"foo": "bar", "list": ["a", "b", "c"]},
            ),
        ],
    )


def test_upload_dry_run(requests_mock):
    """An upload dry run shouldn't make any requests"""
    do_upload_test(
        requests_mock,
        uploader_kwargs={
            "dry_run": True,
        },
        records=[
            Record(
                data={"id": "test-0"},
                attachment={"foo": "bar"},
            ),
            Record(
                data={"id": "test-1", "type": "test-type"},
                attachment={"foo": "bar", "list": ["a", "b", "c"]},
            ),
        ],
        expected_records=[],
    )


def test_delete_if_none(requests_mock):
    """Tests a delete_if that doesn't delete any records"""
    do_delete_if_test(
        requests_mock,
        predicate=lambda r: False,
        expected_deleted_records=[],
    )


def test_delete_if_some(requests_mock):
    """Tests a delete_if that deletes some records"""
    do_delete_if_test(
        requests_mock,
        predicate=lambda r: r.get("type") == "test-type-aaa",
        expected_deleted_records=[
            Record(
                data={"id": "test-1", "type": "test-type-aaa"},
                attachment=["test-1-aaa", "test-1-bbb"],
            ),
            Record(
                data={"id": "test-3", "type": "test-type-aaa"},
                attachment=["test-3-aaa", "test-3-bbb"],
            ),
        ],
    )


def test_delete_if_all(requests_mock):
    """Tests a delete_if that deletes all records"""
    do_delete_if_test(
        requests_mock,
        predicate=lambda r: True,
        expected_deleted_records=[
            Record(
                data={"id": "test-0"},
                attachment=["test-0-aaa", "test-0-bbb"],
            ),
            Record(
                data={"id": "test-1", "type": "test-type-aaa"},
                attachment=["test-1-aaa", "test-1-bbb"],
            ),
            Record(
                data={"id": "test-2", "type": "test-type-bbb"},
                attachment=["test-2-aaa", "test-2-bbb"],
            ),
            Record(
                data={"id": "test-3", "type": "test-type-aaa"},
                attachment=["test-3-aaa", "test-3-bbb"],
            ),
        ],
    )


def test_delete_if_dry_run(requests_mock):
    """A delete_if dry run shouldn't make any requests"""
    do_delete_if_test(
        requests_mock,
        uploader_kwargs={
            "dry_run": True,
        },
        predicate=lambda r: True,
        expected_deleted_records=[],
    )
