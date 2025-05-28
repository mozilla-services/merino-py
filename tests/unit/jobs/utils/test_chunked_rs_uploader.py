# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for chunked_rs_uploader.py."""

from typing import Any


from merino.jobs.csv_rs_uploader import ChunkedRemoteSettingsSuggestionUploader
from tests.unit.jobs.utils.rs_utils import (
    Record as BaseRecord,
    check_upload_requests,
    mock_responses,
    SERVER_DATA,
)

TEST_UPLOADER_KWARGS: dict[str, Any] = SERVER_DATA | {
    "record_type": "test-record-type",
}


class Record(BaseRecord):
    """Remote settings record for a chunked upload."""

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
        attachment: list[dict[str, Any]] = [{"i": i} for i in range(start_index, size)]
        if suggestion_score:
            for suggestion in attachment:
                suggestion["score"] = suggestion_score
        super().__init__(
            data={
                "id": id or f"{type}-{start_index}-{size}",
                "type": type,
            },
            attachment=attachment,
            bucket=bucket,
            collection=collection,
            server=server,
        )


def do_upload_test(
    requests_mock,
    chunk_size: int,
    suggestion_count: int,
    expected_records: list[BaseRecord],
    uploader_kwargs: dict[str, Any] = {},
    suggestion_score: float | None = None,
) -> None:
    """Perform an upload test."""
    mock_responses(requests_mock, expected_records)

    with ChunkedRemoteSettingsSuggestionUploader(
        chunk_size=chunk_size,
        **(TEST_UPLOADER_KWARGS | uploader_kwargs),
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


def test_total_item_count(requests_mock):
    """Tests passing a total suggestion count so record IDs contain zero-padded
    start and end indexes.
    """
    record_type = TEST_UPLOADER_KWARGS["record_type"]
    do_upload_test(
        requests_mock,
        chunk_size=500,
        suggestion_count=1999,
        uploader_kwargs={
            "total_item_count": 1999,
        },
        expected_records=[
            Record(0, 500, id=f"{record_type}-0000-0500"),
            Record(500, 1000, id=f"{record_type}-0500-1000"),
            Record(1000, 1500, id=f"{record_type}-1000-1500"),
            Record(1500, 1999, id=f"{record_type}-1500-1999"),
        ],
    )
