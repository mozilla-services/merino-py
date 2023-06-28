# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for __init__.py module."""

import pathlib
from typing import Any

from merino.jobs.pocket_rs_uploader import upload

# The CSV file containing the test suggestions data. If you modify the data in
# this file, be sure to keep the following in sync:
# * TEST_SUGGESTION_COUNT
# * TEST_KEYWORD_COUNT
# * expected_add_suggestion_calls()
TEST_CSV_BASENAME = "test.csv"
TEST_CSV_PATH = str(pathlib.Path(__file__).parent / TEST_CSV_BASENAME)

TEST_SUGGESTION_COUNT = 3
TEST_KEYWORD_COUNT = 3


def expected_add_suggestion_calls(
    mocker,
    suggestion_count: int = TEST_SUGGESTION_COUNT,
    keyword_count: int = TEST_KEYWORD_COUNT,
):
    """Return a list of expected `add_suggestion()` calls."""
    calls = []
    for s in range(suggestion_count):
        call: dict[str, Any] = {
            "url": f"http://example.com/pocket-{s}",
            "title": f"Title {s}",
            "description": f"Description {s}",
            "lowConfidenceKeywords": [f"low-{s}-{k}" for k in range(keyword_count)],
            "highConfidenceKeywords": [f"high-{s}-{k}" for k in range(keyword_count)],
        }
        calls.append(mocker.call(call))
    return calls


def do_upload_test(
    mocker,
    delete_existing_records: bool = False,
    score: float = 0.99,
) -> None:
    """Perform an upload test."""
    # Mock the chunked uploader.
    mock_chunked_uploader_ctor = mocker.patch(
        "merino.jobs.pocket_rs_uploader.ChunkedRemoteSettingsUploader"
    )
    mock_chunked_uploader = (
        mock_chunked_uploader_ctor.return_value.__enter__.return_value
    )

    # Do the upload.
    common_kwargs: dict[str, Any] = {
        "auth": "auth",
        "bucket": "bucket",
        "chunk_size": 99,
        "collection": "collection",
        "dry_run": False,
        "record_type": "record_type",
        "server": "server",
    }
    upload(
        **common_kwargs,
        delete_existing_records=delete_existing_records,
        score=score,
        csv_path=TEST_CSV_PATH,
    )

    # Check calls.
    mock_chunked_uploader_ctor.assert_called_once_with(
        **common_kwargs,
        suggestion_score_fallback=score,
        total_suggestion_count=TEST_SUGGESTION_COUNT,
    )

    if delete_existing_records:
        mock_chunked_uploader.delete_records.assert_called_once()
    else:
        mock_chunked_uploader.delete_records.assert_not_called()

    mock_chunked_uploader.add_suggestion.assert_has_calls(
        expected_add_suggestion_calls(mocker)
    )


def test_upload_without_deleting(mocker):
    """Tests `upload(delete_existing_records=False)`"""
    do_upload_test(mocker, delete_existing_records=False)


def test_delete_and_upload(mocker):
    """Tests `upload(delete_existing_records=True)`"""
    do_upload_test(mocker, delete_existing_records=True)


def test_upload_with_score(mocker):
    """Tests `upload(score=float)`"""
    do_upload_test(mocker, score=0.12)
