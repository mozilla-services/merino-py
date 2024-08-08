# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the mdn.py model."""

import pytest
from pydantic import ValidationError

from merino.jobs.csv_rs_uploader import MissingFieldError
from merino.jobs.csv_rs_uploader import fakespot
from tests.unit.jobs.csv_rs_uploader.utils import do_csv_test, do_error_test

MODEL_NAME = "fakespot"

TEST_CSV_ROW = {
    "fakespot_grade": "A",
    "product_id": "test-ABCDEF",
    "rating": "3.6",
    "title": "Brand new widget",
    "product_type": "widget",
    "keywords": "widget",
    "total_reviews": "10",
    "url": "https://example.com/new-widget",
    "score": "8.5",
}


def test_upload(mocker):
    """Suggestions should be added and validated."""
    do_csv_test(
        mocker=mocker,
        model_name=MODEL_NAME,
        csv_rows=[
            {
                "fakespot_grade": "A",
                "product_id": "test-ABCDEF",
                "rating": "3.6",
                "title": "Brand new widget",
                "product_type": "widget",
                "keywords": "widget",
                "total_reviews": "10",
                "url": "https://example.com/new-widget",
                "score": "8.5",
            },
            {
                "fakespot_grade": "B",
                "product_id": "  test-XYZ  ",
                "rating": "3.0",
                "title": "  Refurbished widget  \n  ",
                "product_type": "widget",
                "keywords": "",
                "total_reviews": "15",
                "url": "https://example.com/old-widget",
                "score": "8.2",
            },
        ],
        expected_suggestions=[
            {
                "fakespot_grade": "A",
                "product_id": "test-ABCDEF",
                "rating": 3.6,
                "title": "Brand new widget",
                "product_type": "widget",
                "keywords": "widget",
                "total_reviews": 10,
                "url": "https://example.com/new-widget",
                "score": 8.5,
            },
            {
                "fakespot_grade": "B",
                "product_id": "test-XYZ",
                "rating": 3.0,
                "title": "Refurbished widget",
                "product_type": "widget",
                "keywords": "",
                "total_reviews": 15,
                "url": "https://example.com/old-widget",
                "score": 8.2,
            },
        ],
    )


def test_blocklist(mocker, monkeypatch):
    """Suggestions should be added and validated."""
    monkeypatch.setattr(fakespot, "FAKESPOT_CSV_UPLOADER_BLOCKLIST", {"test-ABCDEF"})
    do_csv_test(
        mocker=mocker,
        model_name=MODEL_NAME,
        csv_rows=[
            {
                "fakespot_grade": "A",
                "product_id": "test-ABCDEF",
                "rating": "3.6",
                "title": "Brand new widget",
                "product_type": "widget",
                "keywords": "widget",
                "total_reviews": "10",
                "url": "https://example.com/new-widget",
                "score": "8.5",
            },
            {
                "fakespot_grade": "B",
                "product_id": "  test-XYZ  ",
                "rating": "3.0",
                "title": "  Refurbished widget  \n  ",
                "product_type": "widget",
                "keywords": "",
                "total_reviews": "15",
                "url": "https://example.com/old-widget",
                "score": "8.2",
            },
        ],
        expected_suggestions=[
            # The only the second item should be here, since the first was in the blocklist
            {
                "fakespot_grade": "B",
                "product_id": "test-XYZ",
                "rating": 3.0,
                "title": "Refurbished widget",
                "product_type": "widget",
                "keywords": "",
                "total_reviews": 15,
                "url": "https://example.com/old-widget",
                "score": 8.2,
            },
        ],
    )


@pytest.fixture
def verify_field_validation_error(mocker):
    """Verify that a value for a field will raise a ValidationError"""

    def verify(field_name, field_value):
        do_error_test(
            mocker,
            model_name=MODEL_NAME,
            csv_rows=[
                {**TEST_CSV_ROW, field_name: field_value},
            ],
            expected_error=ValidationError,
        )

    return verify


@pytest.fixture
def verify_field_required(mocker):
    """Verify that a missing field value will raise a MissingFieldError"""

    def verify(field_name):
        row = {name: value for (name, value) in TEST_CSV_ROW.items() if name != field_name}
        do_error_test(
            mocker,
            model_name=MODEL_NAME,
            csv_rows=[row],
            expected_error=MissingFieldError,
        )

    return verify


def test_fakespot_grade(verify_field_validation_error, verify_field_required):
    """Test validation for the fakespot_grade field"""
    verify_field_required("fakespot_grade")
    verify_field_validation_error("fakespot_grade", "")


def test_product_id(verify_field_validation_error, verify_field_required):
    """Test validation for the product_id field"""
    verify_field_required("product_id")
    verify_field_validation_error("product_id", "")


def test_rating(verify_field_validation_error, verify_field_required):
    """Test validation for the rating field"""
    verify_field_required("rating")
    verify_field_validation_error("rating", "")
    verify_field_validation_error("rating", "four and a half")


def test_title(verify_field_validation_error, verify_field_required):
    """Test validation for the title field"""
    verify_field_required("title")
    verify_field_validation_error("title", "")


def test_total_reviews(verify_field_validation_error, verify_field_required):
    """Test validation for the total_reviews field"""
    verify_field_required("total_reviews")
    verify_field_validation_error("total_reviews", "")
    verify_field_validation_error("total_reviews", "one-hundred")


def test_url(verify_field_validation_error, verify_field_required):
    """Test validation for the url field"""
    verify_field_required("url")
    verify_field_validation_error("url", "")
    verify_field_validation_error("url", "not a valid URL")


def test_score(verify_field_validation_error, verify_field_required):
    """Test validation for the score field"""
    verify_field_required("score")
    verify_field_validation_error("score", "")
    verify_field_validation_error("score", "five and a third")
