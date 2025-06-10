# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# Ignore "F811 Redefinition of unused `downloader_fixture`" in this file
# ruff: noqa: F811

"""Unit tests for alternates.py module and `alternates` command."""

from merino.jobs.geonames_uploader.alternates import (
    _rs_alternates_list,
    _rs_alternate,
    upload_alternates,
    ALTERNATES_LANGUAGES_BY_CLIENT_LOCALE,
)

from merino.jobs.geonames_uploader.downloader import GeonameAlternate

from merino.jobs.geonames_uploader.geonames import _rs_geoname, GeonamesRecord

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
    filter_alternates,
    filter_geonames,
    ALTERNATES_BY_COUNTRY,
    GEONAME_NYC,
    GEONAME_GOESSNITZ,
    SERVER_DATA as GEONAMES_SERVER_DATA,
)


ALTS_RECORD_US_0001_ABBR = Record(
    data={
        "id": "geonames-US-0001-abbr",
        "type": "geonames-alternates",
        "country": "US",
        "language": "abbr",
    },
    attachment={
        "language": "abbr",
        "alternates_by_geoname_id": filter_alternates(
            "US",
            "abbr",
            filter_geonames("US", 1_000),
        ),
    },
)

ALTS_RECORD_US_0001_IATA = Record(
    data={
        "id": "geonames-US-0001-iata",
        "type": "geonames-alternates",
        "country": "US",
        "language": "iata",
    },
    attachment={
        "language": "iata",
        "alternates_by_geoname_id": filter_alternates(
            "US",
            "iata",
            filter_geonames("US", 1_000),
        ),
    },
)


def do_test(
    requests_mock,
    force_reupload: bool,
    country: str,
    locales_by_country: dict[str, list[str]],
    existing_records: list[Record],
    expected_uploaded_records: list[Record],
    expected_deleted_records: list[Record] = [],
    alternates_languages_by_client_locale: dict[
        str, list[str]
    ] = ALTERNATES_LANGUAGES_BY_CLIENT_LOCALE,
    alternates_record_type: str = "geonames-alternates",
    alternates_url_format: str = GEONAMES_SERVER_DATA["alternates_url_format"],
    geonames_record_type: str = "geonames-2",
    rs_auth: str = RS_SERVER_DATA["auth"],
    rs_bucket: str = RS_SERVER_DATA["bucket"],
    rs_collection: str = RS_SERVER_DATA["collection"],
    rs_dry_run: bool = False,
    rs_server: str = RS_SERVER_DATA["server"],
) -> None:
    """Perform an alternates upload test."""
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

    geonames_records = [
        GeonamesRecord(data=r.data, geonames=r.attachment)
        for r in existing_records + expected_deleted_records
        if r.data.get("type") == geonames_record_type
    ]

    alternates_records_by_id = {
        r["id"]: r
        for r in rs_client.get_records()
        if r.get("country") == country and r.get("type") == alternates_record_type
    }

    # Call the upload function.
    upload_alternates(
        country=country,
        existing_alternates_records_by_id=alternates_records_by_id,
        force_reupload=force_reupload,
        geonames_records=geonames_records,
        locales_by_country=locales_by_country,
        alternates_languages_by_client_locale=alternates_languages_by_client_locale,
        alternates_record_type=alternates_record_type,
        alternates_url_format=alternates_url_format,
        geonames_record_type=geonames_record_type,
        rs_client=rs_client,
    )

    # Only check remote settings requests, ignore geonames requests.
    rs_requests = [r for r in requests_mock.request_history if r.url.startswith(rs_server)]

    check_upload_requests(rs_requests, expected_uploaded_records)
    check_delete_requests(rs_requests, expected_deleted_records)


def test_basic_no_existing_record(
    requests_mock,
    downloader_fixture: DownloaderFixture,
):
    """Upload alternates for one country with one client locale with one
    langauge. The alternates record doesn't already exist.

    """
    do_test(
        requests_mock,
        force_reupload=False,
        country="US",
        locales_by_country={
            "US": ["en-US"],
        },
        existing_records=[
            Record(
                data={
                    "id": "geonames-US-0001",
                    "type": "geonames-2",
                    "country": "US",
                    "client_countries": ["US"],
                    "filter_expression": "env.country in ['US']",
                },
                attachment=[_rs_geoname(g) for g in filter_geonames("US", 1_000)],
            ),
        ],
        expected_uploaded_records=[
            ALTS_RECORD_US_0001_ABBR,
            Record(
                data={
                    "id": "geonames-US-0001-en",
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
                        filter_geonames("US", 1_000),
                    ),
                },
            ),
            ALTS_RECORD_US_0001_IATA,
        ],
    )


def test_basic_existing_record_dont_force(
    requests_mock,
    downloader_fixture: DownloaderFixture,
):
    """Upload alternates for one country with one client locale with one
    langauge. The alternates record already exists. Don't force re-upload. No
    mutable requests should be made.

    """
    do_test(
        requests_mock,
        force_reupload=False,
        country="US",
        locales_by_country={
            "US": ["en-US"],
        },
        existing_records=[
            Record(
                data={
                    "id": "geonames-US-0001",
                    "type": "geonames-2",
                    "country": "US",
                    "client_countries": ["US"],
                    "filter_expression": "env.country in ['US']",
                },
                attachment=[_rs_geoname(g) for g in filter_geonames("US", 1_000)],
            ),
            ALTS_RECORD_US_0001_ABBR,
            Record(
                data={
                    "id": "geonames-US-0001-en",
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
                        filter_geonames("US", 1_000),
                    ),
                },
            ),
            ALTS_RECORD_US_0001_IATA,
        ],
        expected_uploaded_records=[],
    )


def test_basic_existing_record_force(
    requests_mock,
    downloader_fixture: DownloaderFixture,
):
    """Upload alternates for one country with one client locale with one
    langauge. The alternates record already exists. Force re-upload.

    """
    alts_en_record = Record(
        data={
            "id": "geonames-US-0001-en",
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
                filter_geonames("US", 1_000),
            ),
        },
    )
    do_test(
        requests_mock,
        force_reupload=True,
        country="US",
        locales_by_country={
            "US": ["en-US"],
        },
        existing_records=[
            Record(
                data={
                    "id": "geonames-US-0001",
                    "type": "geonames-2",
                    "country": "US",
                    "client_countries": ["US"],
                    "filter_expression": "env.country in ['US']",
                },
                attachment=[_rs_geoname(g) for g in filter_geonames("US", 1_000)],
            ),
            alts_en_record,
        ],
        expected_uploaded_records=[
            ALTS_RECORD_US_0001_ABBR,
            alts_en_record,
            ALTS_RECORD_US_0001_IATA,
        ],
    )


def test_many_locales(
    requests_mock,
    downloader_fixture: DownloaderFixture,
):
    """Upload alternates for one country with many client locales"""
    do_test(
        requests_mock,
        force_reupload=False,
        country="US",
        locales_by_country={
            "US": ["en-CA", "en-GB", "en-US"],
        },
        existing_records=[
            Record(
                data={
                    "id": "geonames-US-0001",
                    "type": "geonames-2",
                    "country": "US",
                    "client_countries": ["US"],
                    "filter_expression": "env.country in ['US']",
                },
                attachment=[_rs_geoname(g) for g in filter_geonames("US", 1_000)],
            ),
        ],
        expected_uploaded_records=[
            ALTS_RECORD_US_0001_ABBR,
            Record(
                data={
                    "id": "geonames-US-0001-en",
                    "type": "geonames-alternates",
                    "country": "US",
                    "language": "en",
                    "filter_expression": "env.locale in ['en-CA', 'en-GB', 'en-US']",
                },
                attachment={
                    "language": "en",
                    "alternates_by_geoname_id": filter_alternates(
                        "US",
                        "en",
                        filter_geonames("US", 1_000),
                    ),
                },
            ),
            ALTS_RECORD_US_0001_IATA,
        ],
    )


def test_reupload_locales_changed(
    requests_mock,
    downloader_fixture: DownloaderFixture,
):
    """Upload alternates for one country with many client locales. An alternates
    record for the same partition already exists but with different locales. It
    should be re-uploaded.

    """
    do_test(
        requests_mock,
        force_reupload=False,
        country="US",
        locales_by_country={
            "US": ["en-CA", "en-GB", "en-US"],
        },
        existing_records=[
            Record(
                data={
                    "id": "geonames-US-0001",
                    "type": "geonames-2",
                    "country": "US",
                    "client_countries": ["US"],
                    "filter_expression": "env.country in ['US']",
                },
                attachment=[_rs_geoname(g) for g in filter_geonames("US", 1_000)],
            ),
            Record(
                data={
                    "id": "geonames-US-0001-en",
                    "type": "geonames-alternates",
                    "country": "US",
                    "language": "en",
                    # The filter expression only contains `en-US` and none of
                    # the other `en` locales.
                    "filter_expression": "env.locale in ['en-US']",
                },
                attachment={
                    "language": "en",
                    "alternates_by_geoname_id": filter_alternates(
                        "US",
                        "en",
                        filter_geonames("US", 1_000),
                    ),
                },
            ),
        ],
        expected_uploaded_records=[
            ALTS_RECORD_US_0001_ABBR,
            Record(
                data={
                    "id": "geonames-US-0001-en",
                    "type": "geonames-alternates",
                    "country": "US",
                    "language": "en",
                    "filter_expression": "env.locale in ['en-CA', 'en-GB', 'en-US']",
                },
                attachment={
                    "language": "en",
                    "alternates_by_geoname_id": filter_alternates(
                        "US",
                        "en",
                        filter_geonames("US", 1_000),
                    ),
                },
            ),
            ALTS_RECORD_US_0001_IATA,
        ],
    )


def test_reupload_alternates_data_changed(
    requests_mock,
    downloader_fixture: DownloaderFixture,
):
    """Upload alternates for one country with many client locales. An alternates
    record for the same partition already exists but with different alternates
    data in its attachment. It should be re-uploaded.

    """
    do_test(
        requests_mock,
        force_reupload=False,
        country="US",
        locales_by_country={
            "US": ["en-CA", "en-GB", "en-US"],
        },
        existing_records=[
            Record(
                data={
                    "id": "geonames-US-0001",
                    "type": "geonames-2",
                    "country": "US",
                    "client_countries": ["US"],
                    "filter_expression": "env.country in ['US']",
                },
                attachment=[_rs_geoname(g) for g in filter_geonames("US", 1_000)],
            ),
            Record(
                data={
                    "id": "geonames-US-0001-en",
                    "type": "geonames-alternates",
                    "country": "US",
                    "language": "en",
                    "filter_expression": "env.locale in ['en-CA', 'en-GB', 'en-US']",
                },
                # The attachment has alternates data that's incorrect/out of
                # date. We'll just use some DE alternates.
                attachment={
                    "language": "en",
                    "alternates_by_geoname_id": filter_alternates(
                        "DE",
                        "en",
                        [GEONAME_GOESSNITZ],
                    ),
                },
            ),
        ],
        expected_uploaded_records=[
            ALTS_RECORD_US_0001_ABBR,
            Record(
                data={
                    "id": "geonames-US-0001-en",
                    "type": "geonames-alternates",
                    "country": "US",
                    "language": "en",
                    "filter_expression": "env.locale in ['en-CA', 'en-GB', 'en-US']",
                },
                attachment={
                    "language": "en",
                    "alternates_by_geoname_id": filter_alternates(
                        "US",
                        "en",
                        filter_geonames("US", 1_000),
                    ),
                },
            ),
            ALTS_RECORD_US_0001_IATA,
        ],
    )


def test_no_client_countries_one_country_one_locale(
    requests_mock,
    downloader_fixture: DownloaderFixture,
):
    """There's only one client country with one locale. A geonames record exists
    with no client countries. Upload alternates for it. The alternates record
    should have all client locales, which is just the one.

    """
    do_test(
        requests_mock,
        force_reupload=False,
        country="US",
        locales_by_country={
            # One client locale
            "US": ["en-US"],
        },
        existing_records=[
            Record(
                data={
                    "id": "geonames-US-0001",
                    "type": "geonames-2",
                    "country": "US",
                    # No `client_countries`
                },
                attachment=[_rs_geoname(g) for g in filter_geonames("US", 1_000)],
            ),
        ],
        expected_uploaded_records=[
            ALTS_RECORD_US_0001_ABBR,
            Record(
                data={
                    "id": "geonames-US-0001-en",
                    "type": "geonames-alternates",
                    "country": "US",
                    "language": "en",
                    # The one client locale should be included
                    "filter_expression": "env.locale in ['en-US']",
                },
                attachment={
                    "language": "en",
                    "alternates_by_geoname_id": filter_alternates(
                        "US",
                        "en",
                        filter_geonames("US", 1_000),
                    ),
                },
            ),
            ALTS_RECORD_US_0001_IATA,
        ],
    )


def test_no_client_countries_one_country_many_locales(
    requests_mock,
    downloader_fixture: DownloaderFixture,
):
    """There's only one client country and it has many locales. A geonames
    record exists with no client countries. Upload alternates for it. The
    alternates record should have all client locales, which are the ones just
    for the one client country.

    """
    do_test(
        requests_mock,
        force_reupload=False,
        country="US",
        locales_by_country={
            # Many client locales
            "US": ["en-CA", "en-GB", "en-US"],
        },
        existing_records=[
            Record(
                data={
                    "id": "geonames-US-0001",
                    "type": "geonames-2",
                    "country": "US",
                    # No `client_countries`
                },
                attachment=[_rs_geoname(g) for g in filter_geonames("US", 1_000)],
            ),
        ],
        expected_uploaded_records=[
            ALTS_RECORD_US_0001_ABBR,
            Record(
                data={
                    "id": "geonames-US-0001-en",
                    "type": "geonames-alternates",
                    "country": "US",
                    "language": "en",
                    # All client locales should be included
                    "filter_expression": "env.locale in ['en-CA', 'en-GB', 'en-US']",
                },
                attachment={
                    "language": "en",
                    "alternates_by_geoname_id": filter_alternates(
                        "US",
                        "en",
                        filter_geonames("US", 1_000),
                    ),
                },
            ),
            ALTS_RECORD_US_0001_IATA,
        ],
    )


def test_no_client_countries_many_countries_same_locales(
    requests_mock,
    downloader_fixture: DownloaderFixture,
):
    """There are many client countries with many locales, but the locales are
    the same for all client countries. A geonames record exists with no client
    countries. Upload alternates for it. The alternates record should have all
    client locales.

    """
    do_test(
        requests_mock,
        force_reupload=False,
        country="US",
        locales_by_country={
            # Many countries with the same client locales
            "CA": ["en-CA", "en-GB", "en-US"],
            "US": ["en-CA", "en-GB", "en-US"],
        },
        existing_records=[
            Record(
                data={
                    "id": "geonames-US-0001",
                    "type": "geonames-2",
                    "country": "US",
                    # No `client_countries`
                },
                attachment=[_rs_geoname(g) for g in filter_geonames("US", 1_000)],
            ),
        ],
        expected_uploaded_records=[
            ALTS_RECORD_US_0001_ABBR,
            Record(
                data={
                    "id": "geonames-US-0001-en",
                    "type": "geonames-alternates",
                    "country": "US",
                    "language": "en",
                    # All client locales should be included
                    "filter_expression": "env.locale in ['en-CA', 'en-GB', 'en-US']",
                },
                attachment={
                    "language": "en",
                    "alternates_by_geoname_id": filter_alternates(
                        "US",
                        "en",
                        filter_geonames("US", 1_000),
                    ),
                },
            ),
            ALTS_RECORD_US_0001_IATA,
        ],
    )


def test_no_client_countries_many_countries_different_locales(
    requests_mock,
    downloader_fixture: DownloaderFixture,
):
    """There are many client countries with many diffrent locales. A geonames
    record exists with no client countries. Upload alternates for it. An
    alternates record per parition per language should be created for partitions
    that have alternates in that language.

    """
    do_test(
        requests_mock,
        force_reupload=False,
        country="US",
        locales_by_country={
            # Many countries with different client locales
            "CA": ["en-CA", "en-GB", "en-US"],
            "ES": ["es"],
            "MX": ["es-MX"],
            "US": ["en-CA", "en-GB", "en-US"],
        },
        alternates_languages_by_client_locale={
            **ALTERNATES_LANGUAGES_BY_CLIENT_LOCALE,
            "es": ["es"],
            "es-MX": ["es"],
        },
        existing_records=[
            Record(
                data={
                    "id": "geonames-US-0001",
                    "type": "geonames-2",
                    "country": "US",
                    # No `client_countries`
                },
                attachment=[_rs_geoname(g) for g in filter_geonames("US", 1_000)],
            ),
        ],
        expected_uploaded_records=[
            ALTS_RECORD_US_0001_ABBR,
            # en record with en locales
            Record(
                data={
                    "id": "geonames-US-0001-en",
                    "type": "geonames-alternates",
                    "country": "US",
                    "language": "en",
                    "filter_expression": "env.locale in ['en-CA', 'en-GB', 'en-US']",
                },
                attachment={
                    "language": "en",
                    "alternates_by_geoname_id": filter_alternates(
                        "US",
                        "en",
                        filter_geonames("US", 1_000),
                    ),
                },
            ),
            # es record with es locales
            Record(
                data={
                    "id": "geonames-US-0001-es",
                    "type": "geonames-alternates",
                    "country": "US",
                    "language": "es",
                    "filter_expression": "env.locale in ['es', 'es-MX']",
                },
                attachment={
                    "language": "es",
                    "alternates_by_geoname_id": filter_alternates(
                        "US",
                        "es",
                        filter_geonames("US", 1_000),
                    ),
                },
            ),
            ALTS_RECORD_US_0001_IATA,
        ],
    )


def test_realistic_1(
    requests_mock,
    downloader_fixture: DownloaderFixture,
):
    """Realistic upload test: Geonames records have client countries that map to
    the same alternates language

    """
    do_test(
        requests_mock,
        force_reupload=False,
        country="US",
        locales_by_country={
            "CA": ["en-CA", "en-GB", "en-US"],
            "ES": ["es"],
            "MX": ["es-MX"],
            "US": ["en-CA", "en-GB", "en-US"],
        },
        alternates_languages_by_client_locale={
            **ALTERNATES_LANGUAGES_BY_CLIENT_LOCALE,
            "es": ["es"],
            "es-MX": ["es"],
        },
        existing_records=[
            Record(
                data={
                    "id": "geonames-US-0050-0100",
                    "type": "geonames-2",
                    "country": "US",
                    "client_countries": ["US"],
                    "filter_expression": "env.country in ['US']",
                },
                attachment=[_rs_geoname(g) for g in filter_geonames("US", 50_000, 100_000)],
            ),
            Record(
                data={
                    "id": "geonames-US-0100-1000",
                    "type": "geonames-2",
                    "country": "US",
                    # CA and US map to the same alternates languages
                    "client_countries": ["CA", "US"],
                    "filter_expression": "env.country in ['CA', 'US']",
                },
                attachment=[_rs_geoname(g) for g in filter_geonames("US", 100_000, 1_000_000)],
            ),
            Record(
                data={
                    "id": "geonames-US-1000",
                    "type": "geonames-2",
                    "country": "US",
                },
                attachment=[_rs_geoname(g) for g in filter_geonames("US", 1_000_000)],
            ),
        ],
        expected_uploaded_records=[
            # No "geonames-US-0050-0100-en" because there aren't any alternates
            # for US geonames in the range [50k, 100k) that are different from
            # their geonames' names and ASCII names
            Record(
                data={
                    "id": "geonames-US-0100-1000-en",
                    "type": "geonames-alternates",
                    "country": "US",
                    "language": "en",
                    "filter_expression": "env.locale in ['en-CA', 'en-GB', 'en-US']",
                },
                attachment={
                    "language": "en",
                    "alternates_by_geoname_id": filter_alternates(
                        "US",
                        "en",
                        filter_geonames("US", 100_000, 1_000_000),
                    ),
                },
            ),
            Record(
                data={
                    "id": "geonames-US-1000-abbr",
                    "type": "geonames-alternates",
                    "country": "US",
                    "language": "abbr",
                },
                attachment={
                    "language": "abbr",
                    "alternates_by_geoname_id": filter_alternates(
                        "US",
                        "abbr",
                        filter_geonames("US", 1_000_000),
                    ),
                },
            ),
            Record(
                data={
                    "id": "geonames-US-1000-en",
                    "type": "geonames-alternates",
                    "country": "US",
                    "language": "en",
                    "filter_expression": "env.locale in ['en-CA', 'en-GB', 'en-US']",
                },
                attachment={
                    "language": "en",
                    "alternates_by_geoname_id": filter_alternates(
                        "US",
                        "en",
                        filter_geonames("US", 1_000_000),
                    ),
                },
            ),
            Record(
                data={
                    "id": "geonames-US-1000-es",
                    "type": "geonames-alternates",
                    "country": "US",
                    "language": "es",
                    "filter_expression": "env.locale in ['es', 'es-MX']",
                },
                attachment={
                    "language": "es",
                    "alternates_by_geoname_id": filter_alternates(
                        "US",
                        "es",
                        filter_geonames("US", 1_000_000),
                    ),
                },
            ),
            Record(
                data={
                    "id": "geonames-US-1000-iata",
                    "type": "geonames-alternates",
                    "country": "US",
                    "language": "iata",
                },
                attachment={
                    "language": "iata",
                    "alternates_by_geoname_id": filter_alternates(
                        "US",
                        "iata",
                        filter_geonames("US", 1_000_000),
                    ),
                },
            ),
        ],
    )


def test_realistic_2(
    requests_mock,
    downloader_fixture: DownloaderFixture,
):
    """Realistic upload test: Geonames records have client countries that map to
    different alternates languages

    """
    do_test(
        requests_mock,
        force_reupload=False,
        country="US",
        locales_by_country={
            "CA": ["en-CA", "en-GB", "en-US"],
            "ES": ["es"],
            "MX": ["es-MX"],
            "US": ["en-CA", "en-GB", "en-US"],
        },
        alternates_languages_by_client_locale={
            **ALTERNATES_LANGUAGES_BY_CLIENT_LOCALE,
            "es": ["es"],
            "es-MX": ["es"],
        },
        existing_records=[
            Record(
                data={
                    "id": "geonames-US-0050-0100",
                    "type": "geonames-2",
                    "country": "US",
                    # MX and US map to different alternates languages
                    "client_countries": ["MX", "US"],
                    "filter_expression": "env.country in ['MX', 'US']",
                },
                attachment=[_rs_geoname(g) for g in filter_geonames("US", 50_000, 100_000)],
            ),
            Record(
                data={
                    "id": "geonames-US-0100-1000",
                    "type": "geonames-2",
                    "country": "US",
                    # MX and CA/US map to different alternates languages
                    "client_countries": ["CA", "MX", "US"],
                    "filter_expression": "env.country in ['CA', 'MX', 'US']",
                },
                attachment=[_rs_geoname(g) for g in filter_geonames("US", 100_000, 1_000_000)],
            ),
            Record(
                data={
                    "id": "geonames-US-1000",
                    "type": "geonames-2",
                    "country": "US",
                },
                attachment=[_rs_geoname(g) for g in filter_geonames("US", 1_000_000)],
            ),
        ],
        expected_uploaded_records=[
            Record(
                data={
                    "id": "geonames-US-0100-1000-en",
                    "type": "geonames-alternates",
                    "country": "US",
                    "language": "en",
                    "filter_expression": "env.locale in ['en-CA', 'en-GB', 'en-US']",
                },
                attachment={
                    "language": "en",
                    "alternates_by_geoname_id": filter_alternates(
                        "US",
                        "en",
                        filter_geonames("US", 100_000, 1_000_000),
                    ),
                },
            ),
            Record(
                data={
                    "id": "geonames-US-1000-abbr",
                    "type": "geonames-alternates",
                    "country": "US",
                    "language": "abbr",
                },
                attachment={
                    "language": "abbr",
                    "alternates_by_geoname_id": filter_alternates(
                        "US",
                        "abbr",
                        filter_geonames("US", 1_000_000),
                    ),
                },
            ),
            Record(
                data={
                    "id": "geonames-US-1000-en",
                    "type": "geonames-alternates",
                    "country": "US",
                    "language": "en",
                    "filter_expression": "env.locale in ['en-CA', 'en-GB', 'en-US']",
                },
                attachment={
                    "language": "en",
                    "alternates_by_geoname_id": filter_alternates(
                        "US",
                        "en",
                        filter_geonames("US", 1_000_000),
                    ),
                },
            ),
            Record(
                data={
                    "id": "geonames-US-1000-es",
                    "type": "geonames-alternates",
                    "country": "US",
                    "language": "es",
                    "filter_expression": "env.locale in ['es', 'es-MX']",
                },
                attachment={
                    "language": "es",
                    "alternates_by_geoname_id": filter_alternates(
                        "US",
                        "es",
                        filter_geonames("US", 1_000_000),
                    ),
                },
            ),
            Record(
                data={
                    "id": "geonames-US-1000-iata",
                    "type": "geonames-alternates",
                    "country": "US",
                    "language": "iata",
                },
                attachment={
                    "language": "iata",
                    "alternates_by_geoname_id": filter_alternates(
                        "US",
                        "iata",
                        filter_geonames("US", 1_000_000),
                    ),
                },
            ),
        ],
    )


def test_delete_unused_records(requests_mock, downloader_fixture: DownloaderFixture):
    """Upload new alternates. Old unused alternates records should be deleted."""
    # An existing `en-US` alternates record for a partition that doesn't have a
    # corresponding geoanmes record. It should be deleted.
    existing_en_us_record = Record(
        data={
            "id": "geonames-US-0050-0100-en",
            "type": "geonames-alternates",
            "country": "US",
            "language": "en",
            "filter_expression": "env.locales in ['en-CA', 'en-GB', 'en-US']",
        },
        attachment={
            "language": "en",
            "alternates_by_geoname_id": filter_alternates(
                "US", "en", filter_geonames("US", 50_000, 100_000)
            ),
        },
    )

    # An existing `fr-US` alternates record. `fr` isn't listed in
    # `locales_by_country` for the US, so this record should be deleted.
    existing_fr_us_record = Record(
        data={
            "id": "geonames-US-0001-fr",
            "type": "geonames-alternates",
            "country": "US",
            "language": "fr",
        },
        attachment={
            "language": "fr",
            "alternates_by_geoname_id": filter_alternates(
                "US",
                "fr",
                filter_geonames("US", 1_000),
            ),
        },
    )

    do_test(
        requests_mock,
        force_reupload=False,
        country="US",
        locales_by_country={
            "US": ["en-CA", "en-GB", "en-US"],
        },
        existing_records=[
            Record(
                data={
                    "id": "geonames-US-0001",
                    "type": "geonames-2",
                    "country": "US",
                    "client_countries": ["US"],
                    "filter_expression": "env.country in ['US']",
                },
                attachment=[_rs_geoname(g) for g in filter_geonames("US", 1_000)],
            ),
            existing_en_us_record,
            existing_fr_us_record,
            # This is an alternates record for a different country, not the US,
            # so it shouldn't be deleted.
            Record(
                data={
                    "id": "geonames-DE-0001-de",
                    "type": "geonames-alternates",
                    "country": "DE",
                    "language": "de",
                },
                attachment={
                    "language": "de",
                    "alternates_by_geoname_id": filter_alternates(
                        "DE",
                        "en",
                        filter_geonames("DE", 1_000),
                    ),
                },
            ),
        ],
        expected_uploaded_records=[
            ALTS_RECORD_US_0001_ABBR,
            Record(
                data={
                    "id": "geonames-US-0001-en",
                    "type": "geonames-alternates",
                    "country": "US",
                    "language": "en",
                    "filter_expression": "env.locale in ['en-CA', 'en-GB', 'en-US']",
                },
                attachment={
                    "language": "en",
                    "alternates_by_geoname_id": filter_alternates(
                        "US",
                        "en",
                        filter_geonames("US", 1_000),
                    ),
                },
            ),
            ALTS_RECORD_US_0001_IATA,
        ],
        expected_deleted_records=[
            existing_en_us_record,
            existing_fr_us_record,
        ],
    )


def test_no_geonames_records(requests_mock, downloader_fixture: DownloaderFixture):
    """When there aren't any geonames records for the given country, no records
    should be uploaded and alternates records for the country should be deleted
    since they're unused.

    """
    existing_en_us_record = Record(
        data={
            "id": "geonames-US-0050-0100-en",
            "type": "geonames-alternates",
            "country": "US",
            "language": "en",
            "filter_expression": "env.locales in ['en-CA', 'en-GB', 'en-US']",
        },
        attachment={
            "language": "en",
            "alternates_by_geoname_id": filter_alternates(
                "US",
                "en",
                filter_geonames("US", 50_000, 100_000),
            ),
        },
    )
    do_test(
        requests_mock,
        force_reupload=False,
        country="US",
        locales_by_country={
            "US": ["en-CA", "en-GB", "en-US"],
        },
        existing_records=[
            # No geonames records
            existing_en_us_record,
            # This is an alternates record for a different country, not the US,
            # so it shouldn't be deleted.
            Record(
                data={
                    "id": "geonames-DE-0001-de",
                    "type": "geonames-alternates",
                    "country": "DE",
                    "language": "de",
                },
                attachment={
                    "language": "de",
                    "alternates_by_geoname_id": filter_alternates(
                        "DE",
                        "en",
                        filter_geonames("DE", 1_000),
                    ),
                },
            ),
        ],
        expected_uploaded_records=[],
        expected_deleted_records=[existing_en_us_record],
    )


def test_rs_alternates_list():
    """Test the `_rs_alternates_list` and `_rs_alternate` helper functions. In
    particular, `_rs_alternates_list` relies on `_rs_alternate`, which returns
    `None` when an alternate is the same as its geoname's `name` or
    `ascii_name`. `_rs_alternates_list` should not include `None` values.

    """
    # Use the Goessnitz geoname, which has alternates for its name and ASCII
    # name. First, do some sanity checks:
    #
    # (1) The geoname should have the expected name and ASCII name.
    assert GEONAME_GOESSNITZ.name == "Gößnitz"
    assert GEONAME_GOESSNITZ.ascii_name == "Goessnitz"

    # (2) The alternates data should include the Goessnitz alts.
    alt_tuples = [tup for tup in ALTERNATES_BY_COUNTRY["DE"]["en"] if tup[0] == GEONAME_GOESSNITZ]
    assert len(alt_tuples) == 1
    alts = alt_tuples[0][1]

    # (3) The Goessnitz alts should include the geoname's name and ASCII name.
    assert [a.name for a in alts if a.name == GEONAME_GOESSNITZ.name] == [GEONAME_GOESSNITZ.name]
    assert [a.name for a in alts if a.name == GEONAME_GOESSNITZ.ascii_name] == [
        GEONAME_GOESSNITZ.ascii_name
    ]

    # Now check `_rs_alternates_list`. Goessnitz has one alt that's not its name
    # or ASCII name, and `None` values should not be included.
    assert _rs_alternates_list(
        [
            (
                _rs_geoname(GEONAME_GOESSNITZ),
                [
                    GeonameAlternate("some other name 1"),
                    GeonameAlternate(GEONAME_GOESSNITZ.name),
                    GeonameAlternate("some other name 2"),
                    GeonameAlternate(GEONAME_GOESSNITZ.ascii_name),
                    GeonameAlternate("some other name 3"),
                ],
            )
        ]
    ) == [
        [
            GEONAME_GOESSNITZ.id,
            [
                "some other name 1",
                "some other name 2",
                "some other name 3",
            ],
        ]
    ]


def test_rs_alternate_name_only():
    """Test the `_rs_alternate` helper function"""
    assert _rs_alternate(GeonameAlternate("NYC"), _rs_geoname(GEONAME_NYC)) == "NYC"


def test_rs_alternate_is_preferred():
    """Test the `_rs_alternate` helper function"""
    assert _rs_alternate(
        GeonameAlternate("New York", is_preferred=True), _rs_geoname(GEONAME_NYC)
    ) == {
        "name": "New York",
        "is_preferred": True,
    }


def test_rs_alternate_is_short():
    """Test the `_rs_alternate` helper function"""
    assert _rs_alternate(
        GeonameAlternate("New York", is_short=True), _rs_geoname(GEONAME_NYC)
    ) == {
        "name": "New York",
        "is_short": True,
    }


def test_rs_alternate_is_preferred_and_short():
    """Test the `_rs_alternate` helper function"""
    assert _rs_alternate(
        GeonameAlternate("New York", is_preferred=True, is_short=True), _rs_geoname(GEONAME_NYC)
    ) == {
        "name": "New York",
        "is_preferred": True,
        "is_short": True,
    }


def test_rs_alternate_same_as_geoname_name():
    """Test the `_rs_alternate` helper function"""
    assert _rs_alternate(GeonameAlternate(GEONAME_NYC.name), _rs_geoname(GEONAME_NYC)) is None


def test_rs_alternate_same_as_geoname_name_is_preferred():
    """Test the `_rs_alternate` helper function"""
    assert _rs_alternate(
        GeonameAlternate(GEONAME_NYC.name, is_preferred=True), _rs_geoname(GEONAME_NYC)
    ) == {
        "name": GEONAME_NYC.name,
        "is_preferred": True,
    }


def test_rs_alternate_same_as_geoname_name_is_short():
    """Test the `_rs_alternate` helper function"""
    assert _rs_alternate(
        GeonameAlternate(GEONAME_NYC.name, is_short=True), _rs_geoname(GEONAME_NYC)
    ) == {
        "name": GEONAME_NYC.name,
        "is_short": True,
    }


def test_rs_alternate_same_as_geoname_name_is_preferred_and_short():
    """Test the `_rs_alternate` helper function"""
    assert _rs_alternate(
        GeonameAlternate(GEONAME_NYC.name, is_preferred=True, is_short=True),
        _rs_geoname(GEONAME_NYC),
    ) == {
        "name": GEONAME_NYC.name,
        "is_preferred": True,
        "is_short": True,
    }


def test_rs_alternate_same_as_geoname_ascii_name():
    """Test the `_rs_alternate` helper function"""
    assert (
        _rs_alternate(
            GeonameAlternate(GEONAME_GOESSNITZ.ascii_name), _rs_geoname(GEONAME_GOESSNITZ)
        )
        is None
    )


def test_rs_alternate_same_as_geoname_ascii_name_is_preferred_and_short():
    """Test the `_rs_alternate` helper function"""
    assert _rs_alternate(
        GeonameAlternate(GEONAME_GOESSNITZ.ascii_name, is_preferred=True),
        _rs_geoname(GEONAME_GOESSNITZ),
    ) == {
        "name": GEONAME_GOESSNITZ.ascii_name,
        "is_preferred": True,
    }
