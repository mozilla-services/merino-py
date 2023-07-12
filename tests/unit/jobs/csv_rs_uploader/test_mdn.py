# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the mdn.py model."""

from pydantic import HttpUrl, ValidationError

from merino.jobs.csv_rs_uploader import MissingFieldError
from merino.jobs.csv_rs_uploader.mdn import (
    FIELD_DESC,
    FIELD_KEYWORDS,
    FIELD_TITLE,
    FIELD_URL,
)
from tests.unit.jobs.csv_rs_uploader.utils import do_csv_test, do_error_test

MODEL_NAME = "mdn"

TEST_CSV_ROW = {
    FIELD_URL: "http://example.com/mdn",
    FIELD_TITLE: "Title",
    FIELD_DESC: "Description",
    FIELD_KEYWORDS: "a,b,c",
}


def test_upload(mocker):
    """Suggestions should be added and validated."""
    do_csv_test(
        mocker=mocker,
        model_name=MODEL_NAME,
        csv_rows=[
            {
                FIELD_URL: "http://example.com/mdn/0",
                FIELD_TITLE: "Title 0",
                FIELD_DESC: "Description 0",
                FIELD_KEYWORDS: "aaa,bbb,ccc",
            },
            {
                FIELD_URL: "http://example.com/mdn/1",
                FIELD_TITLE: "      Title\n\r 1 \n",
                FIELD_DESC: "      Description\n\t 1\r\n ",
                FIELD_KEYWORDS: "  XxX  , yYy , ZZZ   ",
            },
        ],
        expected_suggestions=[
            {
                "url": HttpUrl("http://example.com/mdn/0"),
                "title": "Title 0",
                "description": "Description 0",
                "keywords": ["aaa", "bbb", "ccc"],
            },
            {
                "url": HttpUrl("http://example.com/mdn/1"),
                "title": "Title 1",
                "description": "Description 1",
                "keywords": ["xxx", "yyy", "zzz"],
            },
        ],
    )


def test_url_invalid(mocker):
    """An invalid URL should raise a ValidationError"""
    do_error_test(
        mocker,
        model_name=MODEL_NAME,
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
        csv_rows=[
            {
                **TEST_CSV_ROW,
                FIELD_DESC: "",
            },
        ],
        expected_error=ValidationError,
    )


def test_keywords_empty(mocker):
    """An empty keywords should raise a ValidationError"""
    do_error_test(
        mocker,
        model_name=MODEL_NAME,
        csv_rows=[
            {
                **TEST_CSV_ROW,
                FIELD_KEYWORDS: "",
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
        csv_rows=[row],
        expected_error=MissingFieldError,
    )


def test_missing_keywords(mocker):
    """A missing keywords field should raise a MissingFieldError"""
    row = {**TEST_CSV_ROW}
    del row[FIELD_KEYWORDS]
    do_error_test(
        mocker,
        model_name=MODEL_NAME,
        csv_rows=[row],
        expected_error=MissingFieldError,
    )
