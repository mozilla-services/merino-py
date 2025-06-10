# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# Ignore "F811 Redefinition of unused `downloader_fixture`" in this file
# ruff: noqa: F811

"""Unit tests for __init__.py module and `upload` command."""

from merino.jobs.geonames_uploader import _upload, CountryConfig, EN_CLIENT_LOCALES

from merino.jobs.geonames_uploader.alternates import ALTERNATES_LANGUAGES_BY_CLIENT_LOCALE

from merino.jobs.geonames_uploader.geonames import Partition, _rs_geoname

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
    filter_alternates,
    filter_geonames,
    GEONAME_NYC,
    GEONAME_NY_STATE,
    GEONAME_GOESSNITZ,
    SERVER_DATA as GEONAMES_SERVER_DATA,
)


def do_test(
    requests_mock,
    force_reupload: bool,
    configs_by_country: dict[str, CountryConfig],
    expected_uploaded_records: list[Record],
    existing_records: list[Record] = [],
    alternates_languages_by_client_locale: dict[
        str, list[str]
    ] = ALTERNATES_LANGUAGES_BY_CLIENT_LOCALE,
    alternates_record_type: str = "geonames-alternates",
    alternates_url_format: str = GEONAMES_SERVER_DATA["alternates_url_format"],
    geonames_record_type: str = "geonames-2",
    geonames_url_format: str = GEONAMES_SERVER_DATA["geonames_url_format"],
    rs_auth: str = RS_SERVER_DATA["auth"],
    rs_bucket: str = RS_SERVER_DATA["bucket"],
    rs_collection: str = RS_SERVER_DATA["collection"],
    rs_dry_run: bool = False,
    rs_server: str = RS_SERVER_DATA["server"],
) -> None:
    """Perform an upload test."""
    # A `requests_mock.exceptions.NoMockAddress: No mock address` error means
    # there was a request for a record that's not mocked here.
    mock_responses(
        requests_mock,
        get=existing_records + expected_uploaded_records,
        update=expected_uploaded_records,
    )

    # Call the upload function.
    _upload(
        force_reupload=force_reupload,
        configs_by_country=configs_by_country,
        alternates_languages_by_client_locale=alternates_languages_by_client_locale,
        alternates_record_type=alternates_record_type,
        alternates_url_format=alternates_url_format,
        geonames_record_type=geonames_record_type,
        geonames_url_format=geonames_url_format,
        rs_auth=rs_auth,
        rs_bucket=rs_bucket,
        rs_collection=rs_collection,
        rs_dry_run=rs_dry_run,
        rs_server=rs_server,
    )

    # Only check remote settings requests, ignore geonames requests.
    rs_requests = [r for r in requests_mock.request_history if r.url.startswith(rs_server)]

    check_upload_requests(rs_requests, expected_uploaded_records)
    check_delete_requests(rs_requests, [])


def test_simple(requests_mock, downloader_fixture: DownloaderFixture):
    """Simple upload test with one country, one partition, one client locale"""
    do_test(
        requests_mock,
        force_reupload=True,
        configs_by_country={
            "US": CountryConfig(
                geonames_partitions=[
                    Partition(threshold=500_000),
                ],
                supported_client_locales=["en-US"],
            ),
        },
        expected_uploaded_records=[
            Record(
                data={
                    "id": "geonames-US-0500",
                    "type": "geonames-2",
                    "country": "US",
                },
                attachment=[_rs_geoname(g) for g in filter_geonames("US", 500_000)],
            ),
            Record(
                data={
                    "id": "geonames-US-0500-abbr",
                    "type": "geonames-alternates",
                    "country": "US",
                    "language": "abbr",
                },
                attachment={
                    "language": "abbr",
                    "alternates_by_geoname_id": filter_alternates(
                        "US",
                        "abbr",
                        filter_geonames("US", 500_000),
                    ),
                },
            ),
            Record(
                data={
                    "id": "geonames-US-0500-en",
                    "type": "geonames-alternates",
                    "country": "US",
                    "language": "en",
                    "filter_expression": "env.locale in ['en-US']",
                },
                attachment={
                    "language": "en",
                    "alternates_by_geoname_id": filter_alternates(
                        "US",
                        "en",
                        filter_geonames("US", 500_000),
                    ),
                },
            ),
            Record(
                data={
                    "id": "geonames-US-0500-iata",
                    "type": "geonames-alternates",
                    "country": "US",
                    "language": "iata",
                },
                attachment={
                    "language": "iata",
                    "alternates_by_geoname_id": filter_alternates(
                        "US",
                        "iata",
                        filter_geonames("US", 500_000),
                    ),
                },
            ),
        ],
    )


def test_realistic(requests_mock, downloader_fixture: DownloaderFixture):
    """Realistic upload test with multiple many, many partitions, many client
    locales

    """
    # This test heavily depends on the geonames and alternates that are defined
    # in the `geonames_utils.py` test file -- all tests do, but this one does in
    # particular since it selects geonames and alternates in so many countries.
    do_test(
        requests_mock,
        force_reupload=True,
        configs_by_country={
            "CA": CountryConfig(
                geonames_partitions=[
                    Partition(threshold=50_000, client_countries=["CA"]),
                    Partition(threshold=250_000, client_countries=["CA", "US"]),
                    Partition(threshold=500_000),
                ],
                supported_client_locales=EN_CLIENT_LOCALES,
            ),
            "DE": CountryConfig(
                geonames_partitions=[
                    Partition(threshold=50_000, client_countries=["DE"]),
                    Partition(threshold=500_000),
                ],
                supported_client_locales=["de"],
            ),
            "MX": CountryConfig(
                geonames_partitions=[
                    Partition(threshold=50_000, client_countries=["MX"]),
                    Partition(threshold=500_000),
                ],
                supported_client_locales=["es-MX"],
            ),
            "US": CountryConfig(
                geonames_partitions=[
                    Partition(threshold=50_000, client_countries=["US"]),
                    Partition(threshold=250_000, client_countries=["CA", "US"]),
                    Partition(threshold=500_000),
                ],
                supported_client_locales=EN_CLIENT_LOCALES,
            ),
        },
        alternates_languages_by_client_locale={
            "en-CA": ["en", "en-CA"],
            "en-GB": ["en", "en-GB"],
            "en-US": ["en"],
            "en-ZA": ["en"],
            "de": ["de"],
            "es-MX": ["es"],
        },
        expected_uploaded_records=[
            # geonames
            Record(
                data={
                    "id": "geonames-CA-0050-0250",
                    "type": "geonames-2",
                    "country": "CA",
                    "client_countries": ["CA"],
                    "filter_expression": "env.country in ['CA']",
                },
                attachment=[_rs_geoname(g) for g in filter_geonames("CA", 50_000, 250_000)],
            ),
            Record(
                data={
                    "id": "geonames-CA-0250-0500",
                    "type": "geonames-2",
                    "country": "CA",
                    "client_countries": ["CA", "US"],
                    "filter_expression": "env.country in ['CA', 'US']",
                },
                attachment=[_rs_geoname(g) for g in filter_geonames("CA", 250_000, 500_000)],
            ),
            Record(
                data={
                    "id": "geonames-CA-0500",
                    "type": "geonames-2",
                    "country": "CA",
                },
                attachment=[_rs_geoname(g) for g in filter_geonames("CA", 500_000)],
            ),
            Record(
                data={
                    "id": "geonames-DE-0050-0500",
                    "type": "geonames-2",
                    "country": "DE",
                    "client_countries": ["DE"],
                    "filter_expression": "env.country in ['DE']",
                },
                attachment=[_rs_geoname(g) for g in filter_geonames("DE", 50_000, 500_000)],
            ),
            Record(
                data={
                    "id": "geonames-DE-0500",
                    "type": "geonames-2",
                    "country": "DE",
                },
                attachment=[_rs_geoname(g) for g in filter_geonames("DE", 500_000)],
            ),
            Record(
                data={
                    "id": "geonames-MX-0050-0500",
                    "type": "geonames-2",
                    "country": "MX",
                    "client_countries": ["MX"],
                    "filter_expression": "env.country in ['MX']",
                },
                attachment=[_rs_geoname(g) for g in filter_geonames("MX", 50_000, 500_000)],
            ),
            Record(
                data={
                    "id": "geonames-MX-0500",
                    "type": "geonames-2",
                    "country": "MX",
                },
                attachment=[_rs_geoname(g) for g in filter_geonames("MX", 500_000)],
            ),
            Record(
                data={
                    "id": "geonames-US-0050-0250",
                    "type": "geonames-2",
                    "country": "US",
                    "client_countries": ["US"],
                    "filter_expression": "env.country in ['US']",
                },
                attachment=[_rs_geoname(g) for g in filter_geonames("US", 50_000, 250_000)],
            ),
            Record(
                data={
                    "id": "geonames-US-0250-0500",
                    "type": "geonames-2",
                    "country": "US",
                    "client_countries": ["CA", "US"],
                    "filter_expression": "env.country in ['CA', 'US']",
                },
                attachment=[_rs_geoname(g) for g in filter_geonames("US", 250_000, 500_000)],
            ),
            Record(
                data={
                    "id": "geonames-US-0500",
                    "type": "geonames-2",
                    "country": "US",
                },
                attachment=[_rs_geoname(g) for g in filter_geonames("US", 500_000)],
            ),
            # alternates
            Record(
                data={
                    "id": "geonames-US-0250-0500-en",
                    "type": "geonames-alternates",
                    "country": "US",
                    "language": "en",
                    "filter_expression": "env.locale in ['en-CA', 'en-GB', 'en-US', 'en-ZA']",
                },
                attachment={
                    "language": "en",
                    "alternates_by_geoname_id": filter_alternates(
                        "US",
                        "en",
                        filter_geonames("US", 250_000, 500_000),
                    ),
                },
            ),
            Record(
                data={
                    "id": "geonames-US-0500-abbr",
                    "type": "geonames-alternates",
                    "country": "US",
                    "language": "abbr",
                },
                attachment={
                    "language": "abbr",
                    "alternates_by_geoname_id": filter_alternates(
                        "US",
                        "abbr",
                        filter_geonames("US", 500_000),
                    ),
                },
            ),
            Record(
                data={
                    "id": "geonames-US-0500-en",
                    "type": "geonames-alternates",
                    "country": "US",
                    "language": "en",
                    "filter_expression": "env.locale in ['en-CA', 'en-GB', 'en-US', 'en-ZA']",
                },
                attachment={
                    "language": "en",
                    "alternates_by_geoname_id": filter_alternates(
                        "US",
                        "en",
                        filter_geonames("US", 500_000),
                    ),
                },
            ),
            Record(
                data={
                    "id": "geonames-US-0500-es",
                    "type": "geonames-alternates",
                    "country": "US",
                    "language": "es",
                    "filter_expression": "env.locale in ['es-MX']",
                },
                attachment={
                    "language": "es",
                    "alternates_by_geoname_id": filter_alternates(
                        "US",
                        "es",
                        filter_geonames("US", 500_000),
                    ),
                },
            ),
            Record(
                data={
                    "id": "geonames-US-0500-iata",
                    "type": "geonames-alternates",
                    "country": "US",
                    "language": "iata",
                },
                attachment={
                    "language": "iata",
                    "alternates_by_geoname_id": filter_alternates(
                        "US",
                        "iata",
                        filter_geonames("US", 500_000),
                    ),
                },
            ),
        ],
    )


def test_force_reupload_false(requests_mock, downloader_fixture: DownloaderFixture):
    """Existing records shouldn't be re-uploaded when force_reupload=False"""
    do_test(
        requests_mock,
        force_reupload=False,
        configs_by_country={
            "US": CountryConfig(
                geonames_partitions=[
                    Partition(threshold=500_000),
                ],
                supported_client_locales=["en-US"],
            ),
        },
        existing_records=[
            Record(
                data={
                    "id": "geonames-US-0500",
                    "type": "geonames-2",
                    "country": "US",
                },
                attachment=[_rs_geoname(g) for g in filter_geonames("US", 500_000)],
            ),
            Record(
                data={
                    "id": "geonames-US-0500-abbr",
                    "type": "geonames-alternates",
                    "country": "US",
                    "language": "abbr",
                },
                attachment={
                    "language": "abbr",
                    "alternates_by_geoname_id": filter_alternates(
                        "US",
                        "abbr",
                        filter_geonames("US", 500_000),
                    ),
                },
            ),
            Record(
                data={
                    "id": "geonames-US-0500-en",
                    "type": "geonames-alternates",
                    "country": "US",
                    "language": "en",
                    "filter_expression": "env.locale in ['en-US']",
                },
                attachment={
                    "language": "en",
                    "alternates_by_geoname_id": filter_alternates(
                        "US",
                        "en",
                        filter_geonames("US", 500_000),
                    ),
                },
            ),
            Record(
                data={
                    "id": "geonames-US-0500-iata",
                    "type": "geonames-alternates",
                    "country": "US",
                    "language": "iata",
                },
                attachment={
                    "language": "iata",
                    "alternates_by_geoname_id": filter_alternates(
                        "US",
                        "iata",
                        filter_geonames("US", 500_000),
                    ),
                },
            ),
        ],
        expected_uploaded_records=[],
    )


def test_filter_alternates():
    """Test the `filter_alternates` test helper function"""
    # NYC has one alt that's not its name or ASCII name, and `None` values
    # should not be included.
    assert filter_alternates("US", "en", [GEONAME_NYC]) == [
        [GEONAME_NYC.id, [{"name": "New York", "is_preferred": True, "is_short": True}]],
    ]

    # Goessnitz has one alt that's not its name or ASCII name, and `None` values
    # should not be included.
    assert filter_alternates("DE", "en", [GEONAME_GOESSNITZ]) == [
        [GEONAME_GOESSNITZ.id, ["Gössnitz"]],
    ]

    assert filter_alternates("US", "fr", [GEONAME_NY_STATE]) == [
        [GEONAME_NY_STATE.id, ["État de New York"]],
    ]
