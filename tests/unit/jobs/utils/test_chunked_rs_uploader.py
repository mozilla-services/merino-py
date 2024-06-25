# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for chunked_rs_uploader.py."""

import json
from typing import Any

from requests_toolbelt.multipart.decoder import MultipartDecoder

from merino.jobs.csv_rs_uploader import ChunkedRemoteSettingsSuggestionUploader

TEST_UPLOADER_KWARGS: dict[str, Any] = {
    "auth": "Bearer auth",
    "bucket": "test-bucket",
    "collection": "test-collection",
    "record_type": "test-record-type",
    "server": "http://localhost",
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
    suggestion_score: float | None
    url: str

    def __init__(
        self,
        start_index: int,
        size: int,
        bucket: str = TEST_UPLOADER_KWARGS["bucket"],
        collection: str = TEST_UPLOADER_KWARGS["collection"],
        server: str = TEST_UPLOADER_KWARGS["server"],
        type: str = TEST_UPLOADER_KWARGS["record_type"],
        suggestion_score: float | None = None,
        id: str | None = None,
    ):
        self.start_index = start_index
        self.size = size
        self.type = type
        self.suggestion_score = suggestion_score
        self.id = id or f"{type}-{start_index}-{size}"
        self.url = f"{server}/buckets/{bucket}/collections/{collection}/records/{self.id}"
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
            },
        }

    @property
    def expected_attachment_request(self) -> dict[str, Any]:
        """A dict that describes the request that Kinto should receive when the
        uploader uploads an attachment.
        """
        attachment: list[dict[str, Any]] = [{"i": i} for i in range(self.start_index, self.size)]
        if self.suggestion_score:
            for suggestion in attachment:
                suggestion["score"] = self.suggestion_score
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


def check_upload_requests(actual_requests: list, expected_records: list[Record]) -> None:
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
    suggestion_count: int,
    expected_records: list[Record],
    uploader_kwargs: dict[str, Any] = {},
    suggestion_score: float | None = None,
) -> None:
    """Perform an upload test."""
    for record in expected_records:
        requests_mock.put(record.url, json={})  # nosec
        requests_mock.post(record.attachment_url, json={})  # nosec

    with ChunkedRemoteSettingsSuggestionUploader(
        chunk_size=chunk_size,
        **TEST_UPLOADER_KWARGS,
        **uploader_kwargs,
    ) as uploader:
        for i in range(suggestion_count):
            suggestion: dict[str, Any] = {"i": i}
            if suggestion_score:
                suggestion["score"] = suggestion_score
            uploader.add_suggestion(suggestion)

    check_upload_requests(requests_mock.request_history, expected_records)


def test_one_chunk_underfill(requests_mock):
    """Tests one chunk that doesn't fill up."""
    do_upload_test(
        requests_mock,
        chunk_size=10,
        suggestion_count=9,
        expected_records=[
            Record(0, 9),
        ],
    )


def test_one_chunk_filled(requests_mock):
    """Tests one chunk that fills up."""
    do_upload_test(
        requests_mock,
        chunk_size=10,
        suggestion_count=10,
        expected_records=[
            Record(0, 10),
        ],
    )


def test_two_chunks_underfill(requests_mock):
    """Tests two chunks where the second chunk doesn't fill up."""
    do_upload_test(
        requests_mock,
        chunk_size=10,
        suggestion_count=19,
        expected_records=[
            Record(0, 10),
            Record(10, 19),
        ],
    )


def test_two_chunks_filled(requests_mock):
    """Tests two chunks where the second chunk fills up."""
    do_upload_test(
        requests_mock,
        chunk_size=10,
        suggestion_count=20,
        expected_records=[
            Record(0, 10),
            Record(10, 20),
        ],
    )


def test_many_chunks_underfill(requests_mock):
    """Tests many chunks where the final chunk doesn't fill up."""
    do_upload_test(
        requests_mock,
        chunk_size=10,
        suggestion_count=99,
        expected_records=[
            Record(0, 10),
            Record(10, 20),
            Record(20, 30),
            Record(30, 40),
            Record(40, 50),
            Record(50, 60),
            Record(60, 70),
            Record(70, 80),
            Record(80, 90),
            Record(90, 99),
        ],
    )


def test_many_chunks_filled(requests_mock):
    """Tests many chunks where the final chunk fills up."""
    do_upload_test(
        requests_mock,
        chunk_size=10,
        suggestion_count=100,
        expected_records=[
            Record(0, 10),
            Record(10, 20),
            Record(20, 30),
            Record(30, 40),
            Record(40, 50),
            Record(50, 60),
            Record(60, 70),
            Record(70, 80),
            Record(80, 90),
            Record(90, 100),
        ],
    )


def test_dry_run(requests_mock):
    """Tests a dry run."""
    do_upload_test(
        requests_mock,
        chunk_size=10,
        suggestion_count=100,
        uploader_kwargs={
            "dry_run": True,
        },
        expected_records=[],
    )


def test_suggestion_score_fallback(requests_mock):
    """Tests suggestion_score_fallback when scores are not present inside the
    suggestions themselves.
    """
    do_upload_test(
        requests_mock,
        chunk_size=10,
        suggestion_count=10,
        uploader_kwargs={
            "suggestion_score_fallback": 0.12,
        },
        expected_records=[
            Record(0, 10, suggestion_score=0.12),
        ],
    )


def test_suggestion_score_fallback_overridden(requests_mock):
    """Tests suggestion_score_fallback that is overridden by scores inside the
    suggestions.
    """
    do_upload_test(
        requests_mock,
        chunk_size=10,
        suggestion_count=10,
        suggestion_score=0.34,
        uploader_kwargs={
            "suggestion_score_fallback": 0.12,
        },
        expected_records=[
            Record(0, 10, suggestion_score=0.34),
        ],
    )


def test_total_data_count(requests_mock):
    """Tests passing a total suggestion count so record IDs contain zero-padded
    start and end indexes.
    """
    record_type = TEST_UPLOADER_KWARGS["record_type"]
    do_upload_test(
        requests_mock,
        chunk_size=500,
        suggestion_count=1999,
        uploader_kwargs={
            "total_data_count": 1999,
        },
        expected_records=[
            Record(0, 500, id=f"{record_type}-0000-0500"),
            Record(500, 1000, id=f"{record_type}-0500-1000"),
            Record(1000, 1500, id=f"{record_type}-1000-1500"),
            Record(1500, 1999, id=f"{record_type}-1500-1999"),
        ],
    )


def test_delete_records(requests_mock):
    """Tests deleting records."""
    bucket = TEST_UPLOADER_KWARGS["bucket"]
    collection = TEST_UPLOADER_KWARGS["collection"]
    server = TEST_UPLOADER_KWARGS["server"]

    records = [Record(10 * i, 10 * (i + 1)) for i in range(0, 10)]

    # Mock the URL that returns all records. First add an unrelated record to
    # make sure it's not deleted.
    records_url = f"{server}/buckets/{bucket}/collections/{collection}/records"
    records_data = [r.data for r in records]
    records_data.append({"type": "some-other-type", "id": "some-other-id"})
    requests_mock.get(records_url, json={"data": records_data})  # nosec

    # Mock the URL for each individual record so it can be deleted.
    for r in records:
        requests_mock.delete(r.url, json={"data": {}})  # nosec

    with ChunkedRemoteSettingsSuggestionUploader(
        chunk_size=10, **TEST_UPLOADER_KWARGS
    ) as uploader:
        uploader.delete_records()

    # There should be one request to the URL that returns all records plus one
    # request per record for each deletion.
    assert len(requests_mock.request_history) == 1 + len(records)

    check_request(
        requests_mock.request_history.pop(0),
        {
            "method": "GET",
            "url": records_url,
        },
    )

    for r in records:
        check_request(requests_mock.request_history.pop(0), r.expected_delete_request)
