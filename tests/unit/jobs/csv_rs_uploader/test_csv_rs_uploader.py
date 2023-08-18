# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for __init__.py module."""

import pathlib
from typing import Any

import pytest
from click.exceptions import BadParameter
from pydantic import HttpUrl, ValidationError

from merino.jobs.csv_rs_uploader import MissingFieldError, upload
from tests.unit.jobs.csv_rs_uploader.model import (
    FIELD_DESC,
    FIELD_KEYWORDS_HIGH,
    FIELD_KEYWORDS_LOW,
    FIELD_TITLE,
    FIELD_URL,
)
from tests.unit.jobs.csv_rs_uploader.utils import do_csv_test, do_error_test

# The CSV file containing the primary test suggestions data. If you modify this
# file, be sure to keep the following in sync:
# - PRIMARY_SUGGESTION_COUNT
# - PRIMARY_KEYWORD_COUNT
# - expected_primary_suggestions()
PRIMARY_CSV_BASENAME = "test.csv"
PRIMARY_CSV_PATH = str(pathlib.Path(__file__).parent / PRIMARY_CSV_BASENAME)
PRIMARY_SUGGESTION_COUNT = 3
PRIMARY_KEYWORD_COUNT = 3

# The model module used to validate the test suggestions data.
MODEL_NAME = "model"
MODEL_PACKAGE = "tests.unit.jobs.csv_rs_uploader"

TEST_CSV_ROW = {
    FIELD_URL: "http://example.com/",
    FIELD_TITLE: "title",
    FIELD_DESC: "desc",
    FIELD_KEYWORDS_LOW: "low",
    FIELD_KEYWORDS_HIGH: "high",
}

TEST_EXPECTED_SUGGESTION = {
    "url": HttpUrl(TEST_CSV_ROW[FIELD_URL]),
    "title": TEST_CSV_ROW[FIELD_TITLE],
    "description": TEST_CSV_ROW[FIELD_DESC],
    "lowConfidenceKeywords": TEST_CSV_ROW[FIELD_KEYWORDS_LOW].split(","),
    "highConfidenceKeywords": TEST_CSV_ROW[FIELD_KEYWORDS_HIGH].split(","),
}


def expected_primary_suggestions() -> list[dict[str, Any]]:
    """Return a list of expected suggestions for the primary CSV test data in
    `PRIMARY_CSV_PATH`.
    """
    suggestions: list[dict[str, Any]] = []
    for s in range(PRIMARY_SUGGESTION_COUNT):
        suggestions.append(
            {
                "url": HttpUrl(f"http://example.com/pocket-{s}"),
                "title": f"Title {s}",
                "description": f"Description {s}",
                "lowConfidenceKeywords": [
                    f"low-{s}-{k}" for k in range(PRIMARY_KEYWORD_COUNT)
                ],
                "highConfidenceKeywords": [
                    f"high-{s}-{k}" for k in range(PRIMARY_KEYWORD_COUNT)
                ],
            }
        )
    return suggestions


def test_upload_without_deleting(mocker):
    """upload(delete_existing_records=False) with the primary CSV test data"""
    do_csv_test(
        mocker=mocker,
        csv_path=PRIMARY_CSV_PATH,
        model_name=MODEL_NAME,
        model_package=MODEL_PACKAGE,
        expected_suggestions=expected_primary_suggestions(),
        delete_existing_records=False,
    )


def test_delete_and_upload(mocker):
    """upload(delete_existing_records=True) with the primary CSV test data"""
    do_csv_test(
        mocker=mocker,
        csv_path=PRIMARY_CSV_PATH,
        model_name=MODEL_NAME,
        model_package=MODEL_PACKAGE,
        expected_suggestions=expected_primary_suggestions(),
        delete_existing_records=True,
    )


def test_upload_with_score(mocker):
    """upload(score=float) with the primary CSV test data"""
    do_csv_test(
        mocker=mocker,
        csv_path=PRIMARY_CSV_PATH,
        model_name=MODEL_NAME,
        model_package=MODEL_PACKAGE,
        expected_suggestions=expected_primary_suggestions(),
        score=0.12,
    )


def test_title_transform(mocker):
    """Extra whitespace in title should be removed"""
    do_csv_test(
        mocker=mocker,
        model_name=MODEL_NAME,
        model_package=MODEL_PACKAGE,
        csv_rows=[
            {
                **TEST_CSV_ROW,
                FIELD_TITLE: "    Some   value\nwith\r\n  Extra whitespace \n",
            },
        ],
        expected_suggestions=[
            {
                **TEST_EXPECTED_SUGGESTION,
                "title": "Some value with Extra whitespace",
            },
        ],
    )


def test_description_transform(mocker):
    """Extra whitespace in description should be removed"""
    do_csv_test(
        mocker=mocker,
        model_name=MODEL_NAME,
        model_package=MODEL_PACKAGE,
        csv_rows=[
            {
                **TEST_CSV_ROW,
                FIELD_DESC: "    Some   value\nwith\r\n  Extra whitespace \n",
            },
        ],
        expected_suggestions=[
            {
                **TEST_EXPECTED_SUGGESTION,
                "description": "Some value with Extra whitespace",
            },
        ],
    )


def test_lowConfidenceKeywords_transform(mocker):
    """Extra whitespace in lowConfidenceKeywords should be removed, it should
    be lowercased, etc.
    """
    do_csv_test(
        mocker=mocker,
        model_name=MODEL_NAME,
        model_package=MODEL_PACKAGE,
        csv_rows=[
            {
                **TEST_CSV_ROW,
                FIELD_KEYWORDS_LOW: "   AaA\n,b,\r\nCCC,  d  ,e’e",
            },
        ],
        expected_suggestions=[
            {
                **TEST_EXPECTED_SUGGESTION,
                "lowConfidenceKeywords": ["aaa", "b", "ccc", "d", "e'e"],
            },
        ],
    )


def test_highConfidenceKeywords_transform(mocker):
    """Extra whitespace in highConfidenceKeywords should be removed, it should
    be lowercased, etc.
    """
    do_csv_test(
        mocker=mocker,
        model_name=MODEL_NAME,
        model_package=MODEL_PACKAGE,
        csv_rows=[
            {
                **TEST_CSV_ROW,
                FIELD_KEYWORDS_HIGH: "   AaA\n,b,\r\nCCC,  d  ,e’e",
            },
        ],
        expected_suggestions=[
            {
                **TEST_EXPECTED_SUGGESTION,
                "highConfidenceKeywords": ["aaa", "b", "ccc", "d", "e'e"],
            },
        ],
    )


def test_default_record_type(mocker):
    """When the record type isn't specified, the model name should be used"""
    do_csv_test(
        mocker=mocker,
        model_name=MODEL_NAME,
        model_package=MODEL_PACKAGE,
        record_type="",
        expected_record_type=f"{MODEL_NAME}-suggestions",
        csv_rows=[TEST_CSV_ROW],
        expected_suggestions=[TEST_EXPECTED_SUGGESTION],
    )


def test_url_empty(mocker):
    """An empty URL should raise a ValidationError"""
    do_error_test(
        mocker,
        model_name=MODEL_NAME,
        model_package=MODEL_PACKAGE,
        csv_rows=[
            {
                **TEST_CSV_ROW,
                FIELD_URL: "",
            },
        ],
        expected_error=ValidationError,
    )


def test_url_invalid(mocker):
    """An invalid URL should raise a ValidationError"""
    do_error_test(
        mocker,
        model_name=MODEL_NAME,
        model_package=MODEL_PACKAGE,
        csv_rows=[
            {
                **TEST_CSV_ROW,
                FIELD_URL: "not a valid URL",
            },
        ],
        expected_error=ValidationError,
    )


def test_title_empty(mocker):
    """An empty title should raise a ValidationError"""
    do_error_test(
        mocker,
        model_name=MODEL_NAME,
        model_package=MODEL_PACKAGE,
        csv_rows=[
            {
                **TEST_CSV_ROW,
                FIELD_TITLE: "",
            },
        ],
        expected_error=ValidationError,
    )


def test_description_empty(mocker):
    """An empty description should raise a ValidationError"""
    do_error_test(
        mocker,
        model_name=MODEL_NAME,
        model_package=MODEL_PACKAGE,
        csv_rows=[
            {
                **TEST_CSV_ROW,
                FIELD_DESC: "",
            },
        ],
        expected_error=ValidationError,
    )


def test_lowConfidenceKeywords_empty(mocker):
    """An empty lowConfidenceKeywords should raise a ValidationError"""
    do_error_test(
        mocker,
        model_name=MODEL_NAME,
        model_package=MODEL_PACKAGE,
        csv_rows=[
            {
                **TEST_CSV_ROW,
                FIELD_KEYWORDS_LOW: "",
            },
        ],
        expected_error=ValidationError,
    )


def test_highConfidenceKeywords_empty(mocker):
    """An empty highConfidenceKeywords should raise a ValidationError"""
    do_error_test(
        mocker,
        model_name=MODEL_NAME,
        model_package=MODEL_PACKAGE,
        csv_rows=[
            {
                **TEST_CSV_ROW,
                FIELD_KEYWORDS_HIGH: "",
            },
        ],
        expected_error=ValidationError,
    )


def test_missing_url(mocker):
    """A missing URL field should raise a MissingFieldError"""
    row = {**TEST_CSV_ROW}
    del row[FIELD_URL]
    do_error_test(
        mocker,
        model_name=MODEL_NAME,
        model_package=MODEL_PACKAGE,
        csv_rows=[row],
        expected_error=MissingFieldError,
    )


def test_missing_title(mocker):
    """A missing title field should raise a MissingFieldError"""
    row = {**TEST_CSV_ROW}
    del row[FIELD_TITLE]
    do_error_test(
        mocker,
        model_name=MODEL_NAME,
        model_package=MODEL_PACKAGE,
        csv_rows=[row],
        expected_error=MissingFieldError,
    )


def test_missing_description(mocker):
    """A missing description field should raise a MissingFieldError"""
    row = {**TEST_CSV_ROW}
    del row[FIELD_DESC]
    do_error_test(
        mocker,
        model_name=MODEL_NAME,
        model_package=MODEL_PACKAGE,
        csv_rows=[row],
        expected_error=MissingFieldError,
    )


def test_missing_low_keywords(mocker):
    """A missing low confidence keywords field should raise a MissingFieldError"""
    row = {**TEST_CSV_ROW}
    del row[FIELD_KEYWORDS_LOW]
    do_error_test(
        mocker,
        model_name=MODEL_NAME,
        model_package=MODEL_PACKAGE,
        csv_rows=[row],
        expected_error=MissingFieldError,
    )


def test_missing_high_keywords(mocker):
    """A missing high confidence keywords field should raise a MissingFieldError"""
    row = {**TEST_CSV_ROW}
    del row[FIELD_KEYWORDS_HIGH]
    do_error_test(
        mocker,
        model_name=MODEL_NAME,
        model_package=MODEL_PACKAGE,
        csv_rows=[row],
        expected_error=MissingFieldError,
    )


def test_missing_csv_path(mocker):
    """An empty csv_path should raise BaseParameter"""
    with pytest.raises(BadParameter):
        upload(
            csv_path="",
            auth="auth",
            bucket="bucket",
            chunk_size=99,
            collection="collection",
            model_name="model_name",
            server="server",
        )


def test_missing_model_name(mocker):
    """An empty model_name should raise BaseParameter"""
    with pytest.raises(BadParameter):
        upload(
            model_name="",
            auth="auth",
            bucket="bucket",
            chunk_size=99,
            collection="collection",
            csv_path="test.csv",
            server="server",
        )


def test_model_not_found(mocker):
    """A model_name that's not found should raise an error"""
    with pytest.raises(ModuleNotFoundError):
        upload(
            model_name="this_does_not_exist",
            model_package=MODEL_PACKAGE,
            csv_path=PRIMARY_CSV_PATH,
            auth="auth",
            bucket="bucket",
            chunk_size=99,
            collection="collection",
            server="server",
        )


def test_model_without_suggestion(mocker):
    """An model.py file without a Suggestion implementation should raise an
    error
    """
    with pytest.raises(AttributeError):
        upload(
            model_name="model_without_suggestion",
            model_package=MODEL_PACKAGE,
            csv_path=PRIMARY_CSV_PATH,
            auth="auth",
            bucket="bucket",
            chunk_size=99,
            collection="collection",
            server="server",
        )


def test_model_without_csv_to_json(mocker):
    """An model.py file without a Suggestion.csv_to_json() implementation should
    raise an error
    """
    with pytest.raises(Exception):
        upload(
            model_name="model_without_csv_to_json",
            model_package=MODEL_PACKAGE,
            csv_path=PRIMARY_CSV_PATH,
            auth="auth",
            bucket="bucket",
            chunk_size=99,
            collection="collection",
            server="server",
        )
