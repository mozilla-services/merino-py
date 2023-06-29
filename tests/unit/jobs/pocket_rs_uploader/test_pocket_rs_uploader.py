# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for __init__.py module."""

import asyncio
import csv
import io
import pathlib
from typing import Any

import pytest
from pydantic import ValidationError

from merino.jobs.pocket_rs_uploader import (
    FIELD_DESC,
    FIELD_KEYWORDS_HIGH,
    FIELD_KEYWORDS_LOW,
    FIELD_TITLE,
    FIELD_URL,
    MissingFieldError,
    _upload_file_object,
    upload,
)

# The CSV file containing the primary test suggestions data. If you modify this
# file, be sure to keep the following in sync:
# - PRIMARY_SUGGESTION_COUNT
# - PRIMARY_KEYWORD_COUNT
# - expected_primary_add_suggestion_calls()
PRIMARY_CSV_BASENAME = "test.csv"
PRIMARY_CSV_PATH = str(pathlib.Path(__file__).parent / PRIMARY_CSV_BASENAME)

PRIMARY_SUGGESTION_COUNT = 3
PRIMARY_KEYWORD_COUNT = 3


def expected_primary_add_suggestion_calls(
    mocker,
    suggestion_count: int = PRIMARY_SUGGESTION_COUNT,
    keyword_count: int = PRIMARY_KEYWORD_COUNT,
):
    """Return a list of expected `add_suggestion()` calls for the primary CSV
    test data in `PRIMARY_CSV_PATH`.
    """
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


def do_primary_upload_test(
    mocker,
    delete_existing_records: bool = False,
    score: float = 0.99,
) -> None:
    """Perform an upload test using the primary CSV test data in
    `PRIMARY_CSV_PATH`.
    """
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
        csv_path=PRIMARY_CSV_PATH,
    )

    # Check calls.
    mock_chunked_uploader_ctor.assert_called_once_with(
        **common_kwargs,
        suggestion_score_fallback=score,
        total_suggestion_count=PRIMARY_SUGGESTION_COUNT,
    )

    if delete_existing_records:
        mock_chunked_uploader.delete_records.assert_called_once()
    else:
        mock_chunked_uploader.delete_records.assert_not_called()

    mock_chunked_uploader.add_suggestion.assert_has_calls(
        expected_primary_add_suggestion_calls(mocker)
    )


def test_upload_without_deleting(mocker):
    """upload(delete_existing_records=False) with the primary CSV test data"""
    do_primary_upload_test(mocker, delete_existing_records=False)


def test_delete_and_upload(mocker):
    """upload(delete_existing_records=True) with the primary CSV test data"""
    do_primary_upload_test(mocker, delete_existing_records=True)


def test_upload_with_score(mocker):
    """upload(score=float) with the primary CSV test data"""
    do_primary_upload_test(mocker, score=0.12)


def make_csv_file_object(csv_rows: list[dict[str, str]]) -> io.TextIOWrapper:
    """Return a StringIO that encodes the given CSV rows."""
    f = io.StringIO()
    csv_writer = csv.DictWriter(f, fieldnames=[*csv_rows[0].keys()])
    csv_writer.writeheader()
    for row in csv_rows:
        csv_writer.writerow(row)
    f.seek(0)
    return f


def do_upload_file_object_test(
    mocker,
    file_object: io.TextIOWrapper,
    expected_add_suggestion_calls,
    delete_existing_records: bool = False,
    score: float = 0.99,
) -> None:
    """Perform an upload test using sync_upload_file_object()."""
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
    asyncio.run(
        _upload_file_object(
            **common_kwargs,
            delete_existing_records=delete_existing_records,
            score=score,
            file_object=file_object,
        )
    )

    # Check calls.
    mock_chunked_uploader_ctor.assert_called_once_with(
        **common_kwargs,
        suggestion_score_fallback=score,
        total_suggestion_count=len(expected_add_suggestion_calls),
    )

    if delete_existing_records:
        mock_chunked_uploader.delete_records.assert_called_once()
    else:
        mock_chunked_uploader.delete_records.assert_not_called()

    mock_chunked_uploader.add_suggestion.assert_has_calls(expected_add_suggestion_calls)


def do_transformed_keyword_test(
    mocker,
    fields: dict[str, str],
    expected_call: dict[str, Any],
):
    """Perform a test where the input data contains keywords with uppercase
    chars, leading or trailing space, etc. The uploader should transform these
    keywords so that all chars are lowercased, trailing and leading space is
    removed, etc.
    """
    row = {
        FIELD_URL: "http://example.com/",
        FIELD_TITLE: "title",
        FIELD_DESC: "desc",
        FIELD_KEYWORDS_LOW: "low",
        FIELD_KEYWORDS_HIGH: "high",
        **fields,
    }
    f = make_csv_file_object([row])
    call: dict[str, Any] = {
        "url": row[FIELD_URL],
        "title": row[FIELD_TITLE],
        "description": row[FIELD_DESC],
        "lowConfidenceKeywords": ["low"],
        "highConfidenceKeywords": ["high"],
        **expected_call,
    }
    calls = [mocker.call(call)]
    do_upload_file_object_test(
        mocker,
        file_object=f,
        expected_add_suggestion_calls=calls,
    )
    f.close()


def test_lowConfidenceKeywords_leading_space(mocker):
    """Leading spaces in lowConfidenceKeywords should be removed"""
    do_transformed_keyword_test(
        mocker,
        fields={FIELD_KEYWORDS_LOW: "a,   b,c"},
        expected_call={"lowConfidenceKeywords": ["a", "b", "c"]},
    )


def test_lowConfidenceKeywords_trailing_space(mocker):
    """Trailing spaces in lowConfidenceKeywords should be removed"""
    do_transformed_keyword_test(
        mocker,
        fields={FIELD_KEYWORDS_LOW: "a,b   ,c"},
        expected_call={"lowConfidenceKeywords": ["a", "b", "c"]},
    )


def test_lowConfidenceKeywords_uppercase(mocker):
    """Uppercase chars in lowConfidenceKeywords should be lowercased"""
    do_transformed_keyword_test(
        mocker,
        fields={FIELD_KEYWORDS_LOW: "a,BBB,c"},
        expected_call={"lowConfidenceKeywords": ["a", "bbb", "c"]},
    )


def test_highConfidenceKeywords_leading_space(mocker):
    """Leading spaces in highConfidenceKeywords should be removed"""
    do_transformed_keyword_test(
        mocker,
        fields={FIELD_KEYWORDS_HIGH: "a,   b,c"},
        expected_call={"highConfidenceKeywords": ["a", "b", "c"]},
    )


def test_highConfidenceKeywords_trailing_space(mocker):
    """Trailing spaces in highConfidenceKeywords should be removed"""
    do_transformed_keyword_test(
        mocker,
        fields={FIELD_KEYWORDS_HIGH: "a,b   ,c"},
        expected_call={"highConfidenceKeywords": ["a", "b", "c"]},
    )


def test_highConfidenceKeywords_uppercase(mocker):
    """Uppercase chars in highConfidenceKeywords should be highercased"""
    do_transformed_keyword_test(
        mocker,
        fields={FIELD_KEYWORDS_HIGH: "a,BBB,c"},
        expected_call={"highConfidenceKeywords": ["a", "bbb", "c"]},
    )


def do_validation_error_test(mocker, fields: dict[str, str]):
    """Perform a test that should raise a ValidationError."""
    row = {
        FIELD_URL: "http://example.com/",
        FIELD_TITLE: "title",
        FIELD_DESC: "desc",
        FIELD_KEYWORDS_LOW: "low",
        FIELD_KEYWORDS_HIGH: "high",
        **fields,
    }
    f = make_csv_file_object([row])
    with pytest.raises(ValidationError):
        do_upload_file_object_test(
            mocker,
            file_object=f,
            expected_add_suggestion_calls=[],
        )
    f.close()


def test_url_empty(mocker):
    """An empty URL should raise a ValidationError"""
    do_validation_error_test(mocker, {FIELD_URL: ""})


def test_url_invalid(mocker):
    """An invalid URL should raise a ValidationError"""
    do_validation_error_test(mocker, {FIELD_URL: "not a valid URL"})


def test_title_empty(mocker):
    """An empty title should raise a ValidationError"""
    do_validation_error_test(mocker, {FIELD_TITLE: ""})


def test_description_empty(mocker):
    """An empty description should raise a ValidationError"""
    do_validation_error_test(mocker, {FIELD_DESC: ""})


def test_lowConfidenceKeywords_empty(mocker):
    """An empty lowConfidenceKeywords should raise a ValidationError"""
    do_validation_error_test(mocker, {FIELD_KEYWORDS_LOW: ""})


def test_highConfidenceKeywords_empty(mocker):
    """An empty highConfidenceKeywords should raise a ValidationError"""
    do_validation_error_test(mocker, {FIELD_KEYWORDS_HIGH: ""})


def do_missing_field_test(mocker, missing_field: str):
    """Perform a test that should raise a MissingFieldError."""
    row = {
        FIELD_URL: "http://example.com/",
        FIELD_TITLE: "title",
        FIELD_DESC: "desc",
        FIELD_KEYWORDS_LOW: "low",
        FIELD_KEYWORDS_HIGH: "high",
    }
    del row[missing_field]
    f = make_csv_file_object([row])
    with pytest.raises(MissingFieldError):
        do_upload_file_object_test(
            mocker,
            file_object=f,
            expected_add_suggestion_calls=[],
        )
    f.close()


def test_missing_url(mocker):
    """A missing URL field should raise a MissingFieldError"""
    do_missing_field_test(mocker, FIELD_URL)


def test_missing_title(mocker):
    """A missing title field should raise a MissingFieldError"""
    do_missing_field_test(mocker, FIELD_TITLE)


def test_missing_description(mocker):
    """A missing description field should raise a MissingFieldError"""
    do_missing_field_test(mocker, FIELD_DESC)


def test_missing_low_keywords(mocker):
    """A missing low confidence keywords field should raise a MissingFieldError"""
    do_missing_field_test(mocker, FIELD_KEYWORDS_LOW)


def test_missing_high_keywords(mocker):
    """A missing high confidence keywords field should raise a MissingFieldError"""
    do_missing_field_test(mocker, FIELD_KEYWORDS_HIGH)
