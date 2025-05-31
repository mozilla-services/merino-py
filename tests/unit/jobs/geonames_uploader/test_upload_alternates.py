# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# Ignore "F811 Redefinition of unused `downloader_fixture`" in this file
# ruff: noqa: F811

"""Unit tests for alternates.py module and `alternates` command."""

from typing import Any

from merino.jobs.geonames_uploader import alternates as upload_alternates

from merino.jobs.geonames_uploader.alternates import _rs_alternates_list, _rs_alternate

from merino.jobs.geonames_uploader.downloader import Geoname, GeonameAlternate

from merino.jobs.geonames_uploader.geonames import _rs_geoname

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
    ALTERNATES,
    GEONAME_NYC,
    GEONAME_GOESSNITZ,
    SERVER_DATA as GEONAMES_SERVER_DATA,
)


def filter_alternates(
    language: str,
    geonames: list[Geoname],
) -> list[list[int | list[str | None | dict[str, Any]]]]:
    """Filter `ALTERNATES` on a language and geonames and return a list of
    tuples appropriate for including in a remote settings attachment.

    """
    return _rs_alternates_list(
        [
            (_rs_geoname(geoname), alts)
            for geoname, alts in ALTERNATES[language]
            if geoname in geonames
        ]
    )


def do_test(
    requests_mock,
    languages: list[str],
    country: str,
    geonames_records: list[Record],
    expected_uploaded_records: list[Record],
    expected_deleted_records: list[Record] = [],
    existing_alternates_records: list[Record] = [],
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
        geonames_records
        + existing_alternates_records
        + expected_uploaded_records
        + expected_deleted_records,
    )

    # Call the command.
    upload_alternates(
        languages=languages,
        country=country,
        alternates_record_type=alternates_record_type,
        alternates_url_format=alternates_url_format,
        geonames_record_type=geonames_record_type,
        rs_auth=rs_auth,
        rs_bucket=rs_bucket,
        rs_collection=rs_collection,
        rs_dry_run=rs_dry_run,
        rs_server=rs_server,
    )

    # Only check remote settings requests, ignore geonames requests.
    rs_requests = [r for r in requests_mock.request_history if r.url.startswith(rs_server)]

    check_upload_requests(rs_requests, expected_uploaded_records)
    check_delete_requests(rs_requests, expected_deleted_records)


def test_one_lang_one_geonames_record(requests_mock, downloader_fixture: DownloaderFixture):
    """Upload alternates for one language and one geonames record"""
    do_test(
        requests_mock,
        country="US",
        languages=["en"],
        geonames_records=[
            Record(
                data={
                    "id": "geonames-US-1k",
                    "type": "geonames-2",
                    "country": "US",
                    "filter_expression_countries": ["GB", "US"],
                    "filter_expression": "env.country in ['GB', 'US']",
                },
                attachment=[_rs_geoname(g) for g in filter_geonames("US", 1_000)],
            ),
        ],
        expected_uploaded_records=[
            Record(
                data={
                    "id": "geonames-US-1k-en",
                    "type": "geonames-alternates",
                    "country": "US",
                    "language": "en",
                    "filter_expression": "env.country in ['GB', 'US'] && env.locale in ['en', 'en-CA', 'en-GB', 'en-US', 'en-ZA']",
                },
                attachment={
                    "language": "en",
                    "alternates_by_geoname_id": filter_alternates(
                        "en",
                        filter_geonames("US", 1_000),
                    ),
                },
            ),
        ],
    )


def test_one_lang_two_geonames_records(requests_mock, downloader_fixture: DownloaderFixture):
    """Upload alternates for one language and two geonames records"""
    do_test(
        requests_mock,
        country="US",
        languages=["en"],
        geonames_records=[
            Record(
                data={
                    "id": "geonames-US-50k-1m",
                    "type": "geonames-2",
                    "country": "US",
                    "filter_expression_countries": ["GB", "US"],
                    "filter_expression": "env.country in ['GB', 'US']",
                },
                attachment=[_rs_geoname(g) for g in filter_geonames("US", 50_000, 1_000_000)],
            ),
            Record(
                data={
                    "id": "geonames-US-1m",
                    "type": "geonames-2",
                    "country": "US",
                    "filter_expression_countries": ["GB", "US"],
                    "filter_expression": "env.country in ['GB', 'US']",
                },
                attachment=[_rs_geoname(g) for g in filter_geonames("US", 1_000_000)],
            ),
        ],
        expected_uploaded_records=[
            # No `geonames-US-50k-1m-en` record because all "en" alternates for
            # geonames in the range [50k, 1m) are the same as their geonames'
            # names.
            Record(
                data={
                    "id": "geonames-US-1m-en",
                    "type": "geonames-alternates",
                    "country": "US",
                    "language": "en",
                    "filter_expression": "env.country in ['GB', 'US'] && env.locale in ['en', 'en-CA', 'en-GB', 'en-US', 'en-ZA']",
                },
                attachment={
                    "language": "en",
                    "alternates_by_geoname_id": filter_alternates(
                        "en",
                        filter_geonames("US", 1_000_000),
                    ),
                },
            ),
        ],
    )


def test_three_langs(requests_mock, downloader_fixture: DownloaderFixture):
    """Upload alternates for three languages, not all of which have alternates"""
    do_test(
        requests_mock,
        country="US",
        # There are no "de" alternates for the US, and "abbr" alternates exist
        # only for geonames with large populations.
        languages=["abbr", "de", "en"],
        geonames_records=[
            Record(
                data={
                    "id": "geonames-US-50k-1m",
                    "type": "geonames-2",
                    "country": "US",
                    "filter_expression_countries": ["GB", "US"],
                    "filter_expression": "env.country in ['GB', 'US']",
                },
                attachment=[_rs_geoname(g) for g in filter_geonames("US", 50_000, 1_000_000)],
            ),
            Record(
                data={
                    "id": "geonames-US-1m",
                    "type": "geonames-2",
                    "country": "US",
                    "filter_expression_countries": ["GB", "US"],
                    "filter_expression": "env.country in ['GB', 'US']",
                },
                attachment=[_rs_geoname(g) for g in filter_geonames("US", 1_000_000)],
            ),
        ],
        expected_uploaded_records=[
            # No `geonames-US-50k-1m-en` record because all "en" alternates for
            # geonames in the range [50k, 1m) are the same as their geonames'
            # names.
            #
            # No `geonames-US-50k-1m-abbr` record because "abbr" alternates
            # exist only for geonames with >= 1m
            #
            # No `geonames-US-50k-1m-de` and `geonames-US-1m-de` records because
            # there are no "de" alternates
            Record(
                data={
                    "id": "geonames-US-1m-abbr",
                    "type": "geonames-alternates",
                    "country": "US",
                    "language": "abbr",
                    # No locales filter
                    "filter_expression": "env.country in ['GB', 'US']",
                },
                attachment={
                    "language": "abbr",
                    "alternates_by_geoname_id": filter_alternates(
                        "abbr",
                        filter_geonames("US", 1_000_000),
                    ),
                },
            ),
            Record(
                data={
                    "id": "geonames-US-1m-en",
                    "type": "geonames-alternates",
                    "country": "US",
                    "language": "en",
                    "filter_expression": "env.country in ['GB', 'US'] && env.locale in ['en', 'en-CA', 'en-GB', 'en-US', 'en-ZA']",
                },
                attachment={
                    "language": "en",
                    "alternates_by_geoname_id": filter_alternates(
                        "en",
                        filter_geonames("US", 1_000_000),
                    ),
                },
            ),
        ],
    )


def test_delete_old_record(requests_mock, downloader_fixture: DownloaderFixture):
    """Upload new alternates, leaving one old alternates record that should be
    deleted

    """
    existing_en_us_record = Record(
        data={
            "id": "geonames-US-50k-en",
            "type": "geonames-alternates",
            "country": "US",
            "language": "en",
            "filter_expression": "env.country in ['GB', 'US'] && env.locales in ['en', 'GB', 'US']",
        },
        attachment={
            "language": "en",
            "alternates_by_geoname_id": filter_alternates("en", filter_geonames("US", 50_000)),
        },
    )
    do_test(
        requests_mock,
        country="US",
        languages=["en"],
        geonames_records=[
            Record(
                data={
                    "id": "geonames-US-1k",
                    "type": "geonames-2",
                    "country": "US",
                    "filter_expression_countries": ["US"],
                    "filter_expression": "env.country in ['US']",
                },
                attachment=[_rs_geoname(g) for g in filter_geonames("US", 1_000)],
            ),
        ],
        existing_alternates_records=[
            existing_en_us_record,
            # This record is "abbr" but only "en" was passed to the command, so
            # it shouldn't be deleted.
            Record(
                data={
                    "id": "geonames-US-1k-abbr",
                    "type": "geonames-alternates",
                    "country": "US",
                    "language": "abbr",
                    "filter_expression": "env.country in ['GB', 'US']",
                },
                attachment={
                    "language": "abbr",
                    "alternates_by_geoname_id": filter_alternates(
                        "abbr",
                        filter_geonames("US", 1_000),
                    ),
                },
            ),
        ],
        expected_uploaded_records=[
            Record(
                data={
                    "id": "geonames-US-1k-en",
                    "type": "geonames-alternates",
                    "country": "US",
                    "language": "en",
                    "filter_expression": "env.country in ['US'] && env.locale in ['en', 'en-CA', 'en-GB', 'en-US', 'en-ZA']",
                },
                attachment={
                    "language": "en",
                    "alternates_by_geoname_id": filter_alternates(
                        "en",
                        filter_geonames("US", 1_000),
                    ),
                },
            ),
        ],
        expected_deleted_records=[
            existing_en_us_record,
        ],
    )


def test_no_geonames_records(requests_mock, downloader_fixture: DownloaderFixture):
    """Nothing should happen when there aren't any geonames records for the
    given country

    """
    existing_en_us_record = Record(
        data={
            "id": "geonames-US-50k-en",
            "type": "geonames-alternates",
            "country": "US",
            "language": "en",
            "filter_expression": "env.country in ['GB', 'US'] && env.locales in ['en', 'GB', 'US']",
        },
        attachment={
            "language": "en",
            "alternates_by_geoname_id": filter_alternates(
                "en",
                filter_geonames("US", 50_000),
            ),
        },
    )
    do_test(
        requests_mock,
        country="US",
        languages=["en"],
        geonames_records=[],
        existing_alternates_records=[
            existing_en_us_record,
            # This record is "abbr" but only "en" was passed to the command, so
            # it shouldn't be deleted.
            Record(
                data={
                    "id": "geonames-US-1k-abbr",
                    "type": "geonames-alternates",
                    "country": "US",
                    "language": "abbr",
                    "filter_expression": "env.country in ['GB', 'US']",
                },
                attachment={
                    "language": "abbr",
                    "alternates_by_geoname_id": filter_alternates(
                        "abbr",
                        filter_geonames("US", 1_000),
                    ),
                },
            ),
        ],
        expected_uploaded_records=[],
        expected_deleted_records=[],
    )


def test_geonames_record_without_filter_countries(
    requests_mock, downloader_fixture: DownloaderFixture
):
    """Test upload with a geonames record for the given country that doesn't
    have any filter-expression countries

    """
    do_test(
        requests_mock,
        country="US",
        languages=["en"],
        geonames_records=[
            Record(
                data={
                    "id": "geonames-US-1k",
                    "type": "geonames-2",
                    "country": "US",
                    # No `filter_expression_countries` or `filter_expression`
                },
                attachment=[_rs_geoname(g) for g in filter_geonames("US", 1_000)],
            ),
        ],
        expected_uploaded_records=[
            Record(
                data={
                    "id": "geonames-US-1k-en",
                    "type": "geonames-alternates",
                    "country": "US",
                    "language": "en",
                    "filter_expression": "env.locale in ['en', 'en-CA', 'en-GB', 'en-US', 'en-ZA']",
                },
                attachment={
                    "language": "en",
                    "alternates_by_geoname_id": filter_alternates(
                        "en",
                        filter_geonames("US", 1_000),
                    ),
                },
            ),
        ],
    )


def test_rs_alternates_list():
    """Test the `filter_alternates` and `_rs_alternates_list` helper functions.
    In particular, `_rs_alternates_list` relies on `_rs_alternate`, which
    returns `None` when an alternate is the same as its geoname's `name` or
    `ascii_name`. `_rs_alternates_list` should not include `None` values.

    """
    # Use the Goessnitz geoname, which has alternates for its name and ASCII
    # name. First, do some sanity checks:
    #
    # (1) The geoname should have the expected name and ASCII name.
    assert GEONAME_GOESSNITZ.name == "Gößnitz"
    assert GEONAME_GOESSNITZ.ascii_name == "Goessnitz"

    # (2) `ALTERNATES` should include the Goessnitz alts.
    alt_tuples = [tup for tup in ALTERNATES["en"] if tup[0] == GEONAME_GOESSNITZ]
    assert len(alt_tuples) == 1
    alts = alt_tuples[0][1]

    # (3) The Goessnitz alts should include the geoname's name and ASCII name.
    assert [a.name for a in alts if a.name == GEONAME_GOESSNITZ.name] == [GEONAME_GOESSNITZ.name]
    assert [a.name for a in alts if a.name == GEONAME_GOESSNITZ.ascii_name] == [
        GEONAME_GOESSNITZ.ascii_name
    ]

    # Now check `filter_alternates`. Goessnitz has one alt that's not its name
    # or ASCII name, and `None` values should not be included.
    assert filter_alternates("en", [GEONAME_GOESSNITZ]) == [
        [GEONAME_GOESSNITZ.id, ["Gössnitz"]],
    ]

    # Check `_rs_alternates_list` directly for good measure.
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
