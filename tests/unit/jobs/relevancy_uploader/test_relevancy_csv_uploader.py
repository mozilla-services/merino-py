# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for __init__.py module."""
import base64
import pathlib
from hashlib import md5
from typing import Any

import pytest
from click.exceptions import BadParameter

from merino.jobs.csv_rs_uploader import upload
from tests.unit.jobs.relevancy_uploader.utils import do_csv_test, do_error_test

# The CSV file containing the primary test relevancy data. If you modify this
# file, be sure to keep the following in sync:
# - PRIMARY_DATA_COUNT
# - expected_relevancy_data()
PRIMARY_CSV_BASENAME = "test_relevancy_data.csv"
PRIMARY_CSV_PATH = str(pathlib.Path(__file__).parent / PRIMARY_CSV_BASENAME)
PRIMARY_DATA_COUNT = 4


def expected_primary_category_data() -> list[dict[str, Any]]:
    """Return a list of expected relevancy domains for the CSV test data in
    `PRIMARY_CSV_PATH` related to the 'Sports' category.
    """
    data: list[dict[str, Any]] = []
    for s in range(PRIMARY_DATA_COUNT):
        md5_hash = md5("sports.com".encode(), usedforsecurity=False).digest()
        data.append({"domain": base64.b64encode(md5_hash).decode()})
    return data


def expected_secondary_category_data() -> list[dict[str, Any]]:
    """Return a list of expected relevancy domains for the CSV test data in
    `PRIMARY_CSV_PATH` related to the 'News' Category.
    """
    md5_hash = md5("sports.com".encode(), usedforsecurity=False).digest()
    return [{"domain": base64.b64encode(md5_hash).decode()}]


def expected_inconclusive_category_data() -> list[dict[str, Any]]:
    """Return a list of expected relevancy domains for the CSV test data in
    `PRIMARY_CSV_PATH` related to the 'Inconclusive' Category.
    """
    md5_hash = md5("inconclusive.com".encode(), usedforsecurity=False).digest()
    return [{"domain": base64.b64encode(md5_hash).decode()}]


def test_upload_without_deleting(mocker):
    """upload(delete_existing_records=False) with the primary CSV test data"""
    do_csv_test(
        mocker=mocker,
        csv_path=PRIMARY_CSV_PATH,
        primary_category_data=expected_primary_category_data(),
        secondary_category_data=expected_secondary_category_data(),
        inconclusive_category_data=expected_inconclusive_category_data(),
        delete_existing_records=False,
    )


def test_delete_and_upload(mocker):
    """upload(delete_existing_records=True) with the primary CSV test data"""
    do_csv_test(
        mocker=mocker,
        csv_path=PRIMARY_CSV_PATH,
        primary_category_data=expected_primary_category_data(),
        secondary_category_data=expected_secondary_category_data(),
        inconclusive_category_data=expected_inconclusive_category_data(),
        delete_existing_records=True,
    )


def test_missing_domain(mocker):
    """A missing domain field should raise a KeyError"""
    row = {
        "rank": 0,
        "host": "sports0.sports.com",
        "origin": "https://sports0.sports.com",
        "suffix": "com",
        "categories": "[Sports]",
    }

    do_error_test(
        mocker,
        csv_rows=[row],
        expected_error=KeyError,
    )


def test_missing_categories(mocker):
    """A missing domain field should raise a KeyError"""
    row = {
        "rank": 0,
        "domain": "sports.com",
        "host": "sports0.sports.com",
        "origin": "https: // sport0.sports.com",
        "suffix": "com",
    }

    do_error_test(
        mocker,
        csv_rows=[row],
        expected_error=KeyError,
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
