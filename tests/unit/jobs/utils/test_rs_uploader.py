# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for rs_uploader.py."""

import json
from typing import Any, Callable

from requests_toolbelt.multipart.decoder import MultipartDecoder

from merino.jobs.utils.rs_uploader import RemoteSettingsUploader

from tests.unit.jobs.utils.rs_utils import Record, check_request, check_delete_requests, check_upload_requests, mock_responses, SERVER_DATA

TEST_UPLOADER_KWARGS = SERVER_DATA

def do_upload_test(
    requests_mock,
    records: list[Record],
    expected_records: list[Record] | None = None,
    uploader_kwargs: dict[str, Any] = {},
) -> None:
    """Perform an upload test."""
    mock_responses(requests_mock, records)

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

    mock_responses(requests_mock, records)

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
