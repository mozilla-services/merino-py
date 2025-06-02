# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for rs_client.py."""

from typing import Any


from merino.jobs.utils.rs_client import (
    RemoteSettingsClient,
    filter_expression,
    filter_expression_dict,
)

from tests.unit.jobs.utils.rs_utils import (
    Record,
    check_delete_requests,
    check_upload_requests,
    mock_responses,
    SERVER_DATA,
)

TEST_CLIENT_KWARGS = SERVER_DATA

TEST_RECORDS = [
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


def do_get_records_test(
    requests_mock,
    expected_records: list[Record],
    client_kwargs: dict[str, Any] = {},
) -> None:
    """Perform a get_records and download_attachment test."""
    mock_responses(requests_mock, TEST_RECORDS)

    client = RemoteSettingsClient(**(TEST_CLIENT_KWARGS | client_kwargs))
    actual_records = client.get_records()

    # Check the records minus the `attachment` metadata.
    actual_data = [{k: v for k, v in r.items() if k != "attachment"} for r in actual_records]
    expected_data = [r.data for r in expected_records]
    assert actual_data == expected_data

    # Download each attachment and compare.
    for actual, expected in zip(actual_records, expected_records):
        actual_attachment = client.download_attachment(actual)
        assert actual_attachment == expected.attachment


def do_upload_test(
    requests_mock,
    records: list[Record],
    expected_records: list[Record] | None = None,
    client_kwargs: dict[str, Any] = {},
) -> None:
    """Perform an upload test."""
    mock_responses(requests_mock, records)

    client = RemoteSettingsClient(**(TEST_CLIENT_KWARGS | client_kwargs))
    for record in records:
        client.upload(record=record.data, attachment=record.attachment)

    expected_records = expected_records if expected_records is not None else records
    check_upload_requests(requests_mock.request_history, expected_records)


def do_delete_test(
    requests_mock,
    record_ids: list[str],
    expected_deleted_records: list[Record],
    client_kwargs: dict[str, Any] = {},
) -> None:
    """Perform a delete test."""
    mock_responses(requests_mock, TEST_RECORDS)

    client = RemoteSettingsClient(**(TEST_CLIENT_KWARGS | client_kwargs))
    for record_id in record_ids:
        client.delete_record(record_id)

    check_delete_requests(requests_mock.request_history, expected_deleted_records)


def test_get_records(requests_mock):
    """Basic get_records test"""
    do_get_records_test(
        requests_mock,
        expected_records=TEST_RECORDS,
    )


def test_get_records_dry_run(requests_mock):
    """Dry run shouldn't prevent getting records and downloading attachments"""
    do_get_records_test(
        requests_mock,
        client_kwargs={
            "dry_run": True,
        },
        expected_records=TEST_RECORDS,
    )


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
        client_kwargs={
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


def test_delete_none(requests_mock):
    """Tests a delete that doesn't delete any records"""
    do_delete_test(
        requests_mock,
        record_ids=[],
        expected_deleted_records=[],
    )


def test_delete_some(requests_mock):
    """Tests a delete that deletes some records"""
    do_delete_test(
        requests_mock,
        record_ids=["test-1", "test-3"],
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


def test_delete_dry_run(requests_mock):
    """A delete dry run shouldn't delete anything"""
    do_delete_test(
        requests_mock,
        client_kwargs={
            "dry_run": True,
        },
        record_ids=["test-1", "test-3"],
        expected_deleted_records=[],
    )


def test_filter_expression_none():
    """Test `filter_expression` function with no countries or locales"""
    assert filter_expression() == ""


def test_filter_expression_one_country():
    """Test `filter_expression` function with one country"""
    assert filter_expression(countries=["US"]) == "env.country in ['US']"


def test_filter_expression_some_countries():
    """Test `filter_expression` function with some countries"""
    assert filter_expression(countries=["US", "GB"]) == "env.country in ['GB', 'US']"


def test_filter_expression_one_locale():
    """Test `filter_expression` function with one locale"""
    assert filter_expression(locales=["en-US"]) == "env.locale in ['en-US']"


def test_filter_expression_some_locale():
    """Test `filter_expression` function with some locales"""
    assert filter_expression(locales=["en-US", "en-GB"]) == "env.locale in ['en-GB', 'en-US']"


def test_filter_expression_some_countries_and_locales():
    """Test `filter_expression` function with some countries and locales"""
    assert (
        filter_expression(countries=["US", "GB"], locales=["en-US", "en-GB"])
        == "env.country in ['GB', 'US'] && env.locale in ['en-GB', 'en-US']"
    )


def test_filter_expression_dict_none():
    """Test `filter_expression_dict` function with no countries or locales"""
    assert filter_expression_dict() == {}


def test_filter_expression_dict_some():
    """Test `filter_expression_dict` function with some countries and locales"""
    assert filter_expression_dict(countries=["US", "GB"], locales=["en-US", "en-GB"]) == {
        "filter_expression": "env.country in ['GB', 'US'] && env.locale in ['en-GB', 'en-US']"
    }
