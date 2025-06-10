# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# Ignore "F811 Redefinition of unused `downloader_fixture`" in this file
# ruff: noqa: F811

"""Unit tests for geonames.py module and `geonames` command."""

from merino.jobs.geonames_uploader.geonames import (
    _rs_geoname,
    _record_id,
    Partition,
    upload_geonames,
    GeonamesRecord,
)

from merino.jobs.utils.rs_client import RemoteSettingsClient

from tests.unit.jobs.utils.rs_utils import (
    Record,
    check_delete_requests,
    check_upload_requests,
    mock_responses,
    SERVER_DATA as RS_SERVER_DATA,
)
from tests.unit.jobs.geonames_uploader.geonames_utils import (
    DownloaderFixture,
    downloader_fixture,  # noqa: F401
    filter_geonames,
    GEONAME_NYC,
    GEONAME_GOESSNITZ,
    SERVER_DATA as GEONAMES_SERVER_DATA,
)


def do_test(
    requests_mock,
    force_reupload: bool,
    country: str,
    partitions: list[Partition],
    expected_uploaded_records: list[Record],
    expected_deleted_records: list[Record] = [],
    existing_records: list[Record] = [],
    geonames_record_type: str = "geonames-2",
    geonames_url_format: str = GEONAMES_SERVER_DATA["geonames_url_format"],
    rs_auth: str = RS_SERVER_DATA["auth"],
    rs_bucket: str = RS_SERVER_DATA["bucket"],
    rs_collection: str = RS_SERVER_DATA["collection"],
    rs_dry_run: bool = False,
    rs_server: str = RS_SERVER_DATA["server"],
) -> None:
    """Perform a geonames upload test."""
    # A `requests_mock.exceptions.NoMockAddress: No mock address` error means
    # there was a request for a record that's not mocked here.
    mock_responses(
        requests_mock,
        get=existing_records,
        update=expected_uploaded_records,
        delete=expected_deleted_records,
    )

    rs_client = RemoteSettingsClient(
        auth=rs_auth,
        bucket=rs_bucket,
        collection=rs_collection,
        server=rs_server,
        dry_run=rs_dry_run,
    )

    geonames_records_by_id = {}
    for record in rs_client.get_records():
        if record.get("country") == country and (record_id := record.get("id")):
            if record.get("type") == geonames_record_type:
                geonames_records_by_id[record_id] = record

    # Call the upload function.
    final_geonames_records = upload_geonames(
        country=country,
        existing_geonames_records_by_id=geonames_records_by_id,
        force_reupload=force_reupload,
        partitions=partitions,
        geonames_record_type=geonames_record_type,
        geonames_url_format=geonames_url_format,
        rs_client=rs_client,
    )

    expected_final_geonames_records = sorted(
        list(
            {
                r.data["id"]: GeonamesRecord(data=r.data, geonames=r.attachment)
                for r in existing_records + expected_uploaded_records
                if r.data["type"] == geonames_record_type and r.attachment
            }.values()
        ),
        key=lambda r: r.data["id"],
    )
    assert final_geonames_records == expected_final_geonames_records

    # Only check remote settings requests, ignore geonames requests.
    rs_requests = [r for r in requests_mock.request_history if r.url.startswith(rs_server)]

    check_upload_requests(rs_requests, expected_uploaded_records)
    check_delete_requests(rs_requests, expected_deleted_records)


def test_one_part_no_filter_countries(
    requests_mock,
    downloader_fixture,
):
    """Upload one partition, no client countries"""
    do_test(
        requests_mock,
        force_reupload=False,
        country="US",
        partitions=[Partition(1_000)],
        expected_uploaded_records=[
            Record(
                data={
                    "id": "geonames-US-0001",
                    "type": "geonames-2",
                    "country": "US",
                },
                attachment=[_rs_geoname(g) for g in filter_geonames("US", 1_000)],
            ),
        ],
    )


def test_one_part_filter_countries(requests_mock, downloader_fixture: DownloaderFixture):
    """Upload one partition with some client countries"""
    do_test(
        requests_mock,
        force_reupload=False,
        country="US",
        partitions=[Partition(1_000, ["GB", "US"])],
        expected_uploaded_records=[
            Record(
                data={
                    "id": "geonames-US-0001",
                    "type": "geonames-2",
                    "country": "US",
                    "client_countries": ["GB", "US"],
                    "filter_expression": "env.country in ['GB', 'US']",
                },
                attachment=[_rs_geoname(g) for g in filter_geonames("US", 1_000)],
            ),
        ],
    )


def test_one_part_empty_1(requests_mock, downloader_fixture: DownloaderFixture):
    """Upload one partition that's empty and has no client countries"""
    do_test(
        requests_mock,
        force_reupload=False,
        country="US",
        partitions=[Partition(999_999_999_999)],
        expected_uploaded_records=[],
    )


def test_one_part_empty_2(requests_mock, downloader_fixture: DownloaderFixture):
    """Upload one partition that's empty and has some client countries"""
    do_test(
        requests_mock,
        force_reupload=False,
        country="US",
        partitions=[Partition(999_999_999_999, ["US", "GB"])],
        expected_uploaded_records=[],
    )


def test_two_parts_first_part_empty_1(
    requests_mock,
    downloader_fixture: DownloaderFixture,
):
    """Upload two partitions, first is empty, second does not have client
    countries

    """
    do_test(
        requests_mock,
        force_reupload=False,
        country="US",
        # There are no US geonames with populations in the range [1k, 10k), so
        # the first partition should not be created.
        partitions=[Partition(1_000, ["US"]), Partition(10_000)],
        expected_uploaded_records=[
            Record(
                data={
                    # There shouldn't be a filter expression since the second
                    # partition doesn't specify any countries -- it should be
                    # available to all clients.
                    "id": "geonames-US-0010",
                    "type": "geonames-2",
                    "country": "US",
                },
                attachment=[_rs_geoname(g) for g in filter_geonames("US", 10_000)],
            ),
        ],
    )


def test_two_parts_first_part_empty_2(
    requests_mock,
    downloader_fixture: DownloaderFixture,
):
    """Upload two partitions, first is empty, second has client countries"""
    do_test(
        requests_mock,
        force_reupload=False,
        country="US",
        # There are no geonames with populations in the range [1k, 10k), so the
        # first partition should not be created.
        partitions=[Partition(1_000, ["US"]), Partition(10_000, ["US", "GB"])],
        expected_uploaded_records=[
            Record(
                data={
                    "id": "geonames-US-0010",
                    "type": "geonames-2",
                    "country": "US",
                    "client_countries": ["GB", "US"],
                    "filter_expression": "env.country in ['GB', 'US']",
                },
                attachment=[_rs_geoname(g) for g in filter_geonames("US", 10_000)],
            ),
        ],
    )


def test_two_parts_neither_empty_1(requests_mock, downloader_fixture: DownloaderFixture):
    """Upload two partitions, neither are empty, second does not have client
    countries

    """
    do_test(
        requests_mock,
        force_reupload=False,
        country="US",
        partitions=[Partition(50_000, ["US"]), Partition(1_000_000)],
        expected_uploaded_records=[
            Record(
                data={
                    "id": "geonames-US-0050-1000",
                    "type": "geonames-2",
                    "country": "US",
                    "client_countries": ["US"],
                    "filter_expression": "env.country in ['US']",
                },
                attachment=[_rs_geoname(g) for g in filter_geonames("US", 50_000, 1_000_000)],
            ),
            Record(
                data={
                    "id": "geonames-US-1000",
                    "type": "geonames-2",
                    "country": "US",
                    # No `client_countries` or `filter_expression` since the
                    # final partition didn't include them
                },
                attachment=[_rs_geoname(g) for g in filter_geonames("US", 1_000_000)],
            ),
        ],
    )


def test_two_parts_neither_empty_2(requests_mock, downloader_fixture: DownloaderFixture):
    """Upload two partitions, neither are empty, second has different client
    countries

    """
    do_test(
        requests_mock,
        force_reupload=False,
        country="US",
        partitions=[Partition(50_000, ["US"]), Partition(1_000_000, ["GB"])],
        expected_uploaded_records=[
            Record(
                data={
                    "id": "geonames-US-0050-1000",
                    "type": "geonames-2",
                    "country": "US",
                    "client_countries": ["US"],
                    "filter_expression": "env.country in ['US']",
                },
                attachment=[_rs_geoname(g) for g in filter_geonames("US", 50_000, 1_000_000)],
            ),
            Record(
                data={
                    "id": "geonames-US-1000",
                    "type": "geonames-2",
                    "country": "US",
                    "client_countries": ["GB"],
                    "filter_expression": "env.country in ['GB']",
                },
                attachment=[_rs_geoname(g) for g in filter_geonames("US", 1_000_000)],
            ),
        ],
    )


def test_two_parts_neither_empty_3(requests_mock, downloader_fixture: DownloaderFixture):
    """Upload two partitions, neither are empty, second has client countries
    with one new country plus the country from the first partition

    """
    do_test(
        requests_mock,
        force_reupload=False,
        country="US",
        partitions=[Partition(50_000, ["US"]), Partition(1_000_000, ["GB", "US"])],
        expected_uploaded_records=[
            Record(
                data={
                    "id": "geonames-US-0050-1000",
                    "type": "geonames-2",
                    "country": "US",
                    "client_countries": ["US"],
                    "filter_expression": "env.country in ['US']",
                },
                attachment=[_rs_geoname(g) for g in filter_geonames("US", 50_000, 1_000_000)],
            ),
            Record(
                data={
                    "id": "geonames-US-1000",
                    "type": "geonames-2",
                    "country": "US",
                    "client_countries": ["GB", "US"],
                    "filter_expression": "env.country in ['GB', 'US']",
                },
                attachment=[_rs_geoname(g) for g in filter_geonames("US", 1_000_000)],
            ),
        ],
    )


def test_existing_record_dont_force(requests_mock, downloader_fixture: DownloaderFixture):
    """Try to update an existing record but with no changes. Don't force
    re-upload. No mutable requests should be made.

    """
    do_test(
        requests_mock,
        force_reupload=False,
        country="US",
        partitions=[Partition(1_000)],
        existing_records=[
            Record(
                data={
                    "id": "geonames-US-0001",
                    "type": "geonames-2",
                    "country": "US",
                },
                attachment=[_rs_geoname(g) for g in filter_geonames("US", 1_000)],
            ),
        ],
        expected_uploaded_records=[],
    )


def test_existing_record_force(requests_mock, downloader_fixture: DownloaderFixture):
    """Try to update an existing record but with no changes. Force re-upload."""
    do_test(
        requests_mock,
        force_reupload=True,
        country="US",
        partitions=[Partition(1_000)],
        existing_records=[
            Record(
                data={
                    "id": "geonames-US-0001",
                    "type": "geonames-2",
                    "country": "US",
                },
                attachment=[_rs_geoname(g) for g in filter_geonames("US", 1_000)],
            ),
        ],
        expected_uploaded_records=[
            Record(
                data={
                    "id": "geonames-US-0001",
                    "type": "geonames-2",
                    "country": "US",
                },
                attachment=[_rs_geoname(g) for g in filter_geonames("US", 1_000)],
            ),
        ],
    )


def test_delete_old_records(requests_mock, downloader_fixture: DownloaderFixture):
    """Upload a record, deleting existing records for the same country"""
    existing_us_records = [
        Record(
            data={
                "id": "geonames-US-0050-0100",
                "type": "geonames-2",
                "country": "US",
            },
            attachment=[],
        ),
        Record(
            data={
                "id": "geonames-US-0100",
                "type": "geonames-2",
                "country": "US",
            },
            attachment=[],
        ),
    ]
    do_test(
        requests_mock,
        force_reupload=False,
        country="US",
        partitions=[Partition(1_000)],
        existing_records=[
            *existing_us_records,
            # A record with a different country should not be deleted.
            Record(
                data={
                    "id": "geonames-GB-1000",
                    "type": "geonames-2",
                    "country": "GB",
                },
                attachment=[],
            ),
        ],
        expected_uploaded_records=[
            Record(
                data={
                    "id": "geonames-US-0001",
                    "type": "geonames-2",
                    "country": "US",
                },
                attachment=[_rs_geoname(g) for g in filter_geonames("US", 1_000)],
            ),
        ],
        expected_deleted_records=existing_us_records,
    )


def test_rs_geoname_nyc():
    """Test the `_rs_geoname` helper function"""
    assert _rs_geoname(GEONAME_NYC) == {
        "id": 5128581,
        "name": "New York City",
        "feature_class": "P",
        "feature_code": "PPL",
        "country": "US",
        "admin1": "NY",
        "population": 8804190,
        "latitude": "40.71427",
        "longitude": "-74.00597",
    }


def test_rs_geoname_goessnitz():
    """Test the `_rs_geoname` helper function"""
    assert _rs_geoname(GEONAME_GOESSNITZ) == {
        "id": 2918770,
        "name": "Gößnitz",
        "ascii_name": "Goessnitz",
        "feature_class": "P",
        "feature_code": "PPL",
        "country": "DE",
        "admin1": "15",
        "admin2": "00",
        "admin3": "16077",
        "admin4": "16077012",
        "population": 4104,
        "latitude": "50.88902",
        "longitude": "12.43292",
    }


def test_record_id_1():
    """Test the `_record_id` helper function"""
    assert _record_id("US", 1) == "geonames-US-0000"


def test_record_id_2():
    """Test the `_record_id` helper function"""
    assert _record_id("US", 1, 50) == "geonames-US-0000-0000"


def test_record_id_1k_1():
    """Test the `_record_id` helper function"""
    assert _record_id("US", 1_000, 5_000) == "geonames-US-0001-0005"


def test_record_id_1k_2():
    """Test the `_record_id` helper function"""
    assert _record_id("US", 1_001, 5_001) == "geonames-US-0001-0005"


def test_record_id_10k_1():
    """Test the `_record_id` helper function"""
    assert _record_id("US", 10_000, 50_000) == "geonames-US-0010-0050"


def test_record_id_10k_2():
    """Test the `_record_id` helper function"""
    assert _record_id("US", 10_001, 50_001) == "geonames-US-0010-0050"


def test_record_id_100k_1():
    """Test the `_record_id` helper function"""
    assert _record_id("US", 100_000, 500_000) == "geonames-US-0100-0500"


def test_record_id_100k_2():
    """Test the `_record_id` helper function"""
    assert _record_id("US", 100_001, 500_001) == "geonames-US-0100-0500"


def test_record_id_1m_1():
    """Test the `_record_id` helper function"""
    assert _record_id("US", 1_000_000, 5_000_000) == "geonames-US-1000-5000"


def test_record_id_1m_2():
    """Test the `_record_id` helper function"""
    assert _record_id("US", 1_000_001, 5_000_001) == "geonames-US-1000-5000"
