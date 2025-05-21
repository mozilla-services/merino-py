# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for __init__.py module."""

#XXXadw all geoname populations below requested threshold

from copy import deepcopy
import json

from itertools import chain
from typing import Any
import unittest

from merino.jobs.geonames_uploader.downloader import (
    DownloadMetrics,
    DownloadState,
    Geoname,

    #XXXadw
    GeonamesDownloader,
)
from merino.jobs.geonames_uploader import upload, _delete_if_predicate, _jsonable_geoname

from tests.unit.jobs.utils.rs_utils import Record, check_upload_requests, mock_responses, SERVER_DATA as RS_SERVER_DATA
from tests.unit.jobs.geonames_uploader.geonames_utils import (
    DownloaderFixture,
    downloader_fixture,
    with_alternates,
    GEONAMES,
    GEONAME_WATERLOO_AL,
    SERVER_DATA as GEONAMES_SERVER_DATA
)


def do_uploader_test(
    mocker,
    requests_mock,
    geonames_countries: list[str],
    population_thresholds: list[int],
    filter_expression_countries: list[str],
    filter_expression_locales: list[str],
    alternates_iso_languages: list[str],
    expected_uploaded_records: list[Record],
    expected_deleted_records: list[Record],
    alternates_record_type: str = "geonames-alternates",
    geonames_record_type: str = "geonames-2",
    keep_existing_records: bool = True,
) -> None:
    """Perform a geonames upload test."""

    # A `requests_mock.exceptions.NoMockAddress: No mock address` error means
    # there was a request for a record that's not in `expected_uploaded_records`
    # or `expected_deleted_records` -- your test is wrong.
    mock_responses(requests_mock, expected_uploaded_records + expected_deleted_records)

    min_threshold = min(population_thresholds)

    # Call the job's `upload()`.
    upload(
        auth=RS_SERVER_DATA["auth"],
        bucket=RS_SERVER_DATA["bucket"],
        collection=RS_SERVER_DATA["collection"],
        dry_run=False,
        server=RS_SERVER_DATA["server"],

        base_url=GEONAMES_SERVER_DATA["base_url"],
        alternates_path=GEONAMES_SERVER_DATA["alternates_path"],
        geonames_path=GEONAMES_SERVER_DATA["geonames_path"],

        alternates_iso_languages=alternates_iso_languages,
        alternates_record_type=alternates_record_type,
        geonames_record_type=geonames_record_type,
        population_thresholds=population_thresholds,
        filter_expression_countries=filter_expression_countries,
        filter_expression_locales=filter_expression_locales,
        geonames_countries=geonames_countries,
        keep_existing_records=keep_existing_records,
    )

    check_upload_requests(
        # Only check remote settings requests, ignore geonames requests
        [r for r in requests_mock.request_history if r.hostname == RS_SERVER_DATA["hostname"]],
        expected_uploaded_records
    )



# def test_upload_without_deleting(mocker, requests_mock, downloader_fixture: DownloaderFixture):
def test_upload_1(mocker, requests_mock, downloader_fixture: DownloaderFixture):
    """XXXadw"""
    do_uploader_test(
        mocker,
        requests_mock,

#         geonames_country="US",
#         population_thresholds=[50_000, 500_000],
#         filter_expression_countries_per_population_threshold=[["US", "CA"], None],
#         # and then you have to run it a second time to download/upload
#         # alternates per natural language, and the list of geonames to download
#         # alternates for is determined by pulling the geonames record from rs


        geonames_countries=["US"],
        filter_expression_countries=["GB", "US"],
        filter_expression_locales=["en-GB", "en-US"],
        population_thresholds=[1],
#         alternates_iso_languages=["abbr", "en", "iata"],
        alternates_iso_languages=["en"],
        #XXXadw
        keep_existing_records=True,
#         keep_existing_records=False,
#         geonames=[
#             with_alternates(GEONAME_WATERLOO_AL, {
#                 "en": ["Waterloo"],
#             }),
#         ],
        expected_uploaded_records=[
            Record(
                data={
                    "id": "geonames-US-1",
                    "type": "geonames-2",
                    "filter_expression": "env.country in ['GB', 'US'] && env.locale in ['en-GB', 'en-US']",
                },
                attachment=[_jsonable_geoname(g) for g in GEONAMES],
            ),
            Record(
                data={
                    "id": "geonames-US-1-en",
                    "type": "geonames-alternates",
                    "filter_expression": "env.country in ['GB', 'US'] && env.locale in ['en-GB', 'en-US']",
                },
                attachment={
                    "language": "en",
                    "names_by_geoname_id": [
#                         {g.id: g.alternates_by_iso_language.get("en")} for g in GEONAMES
                        [g.id, g.alternates_by_iso_language.get("en")] for g in GEONAMES
                    ],
                },
            ),
        ],
        expected_deleted_records=[],
    )





# def test_delete_and_upload(mocker):
#     """upload(keep_existing_records=False)"""
#     do_uploader_test(
#         mocker=mocker,
#         country_codes=["US"],
#         keep_existing_records=False,
#         geonames=[
#             Geoname(
#                 id=1,
#                 name="Waterloo",
#                 latitude="34.91814",
#                 longitude="-88.0642",
#                 feature_class="P",
#                 feature_code="PPL",
#                 country_code="US",
#                 admin1_code="AL",
#                 population=200,
#                 alternates=[GeonameAlternate(1, "waterloo")],
#             ),
#         ],
#     )


# def test_upload_multiple_countries(mocker):
#     """upload() with multiple countries"""
#     do_uploader_test(
#         mocker=mocker,
#         country_codes=["US", "CA"],
#         keep_existing_records=True,
#         geonames=[
#             Geoname(
#                 id=1,
#                 name="Waterloo",
#                 latitude="34.91814",
#                 longitude="-88.0642",
#                 feature_class="P",
#                 feature_code="PPL",
#                 country_code="US",
#                 admin1_code="AL",
#                 population=200,
#                 alternates=[GeonameAlternate(1, "waterloo")],
#             ),
#         ],
#     )


# def test_to_json_serializable():
#     """Test GeonamesChunk.to_json_serializable()"""
#     chunk = GeonamesChunk(0)
#     chunk.add_item(
#         Geoname(
#             id=1,
#             name="Waterloo",
#             latitude="34.91814",
#             longitude="-88.0642",
#             feature_class="P",
#             feature_code="PPL",
#             country_code="US",
#             admin1_code="AL",
#             population=200,
#             alternates=[GeonameAlternate(1, "waterloo")],
#         )
#     )
#     chunk.add_item(
#         Geoname(
#             id=2,
#             name="Alabama",
#             latitude="32.75041",
#             longitude="-86.75026",
#             feature_class="A",
#             feature_code="ADM1",
#             country_code="US",
#             admin1_code="AL",
#             population=4530315,
#             alternates=[GeonameAlternate(2, "alabama"), GeonameAlternate(2, "al", "abbr")],
#         )
#     )
#     # Add a geoname with a long name and many words *last* to make sure
#     # `max_alternate_name_length` and `max_alternate_name_word_count` are
#     # updated correctly.
#     long_name = "A very long name with a lot of different words"
#     chunk.add_item(
#         Geoname(
#             id=3,
#             name=long_name,
#             latitude="0.0",
#             longitude="0.0",
#             feature_class="P",
#             feature_code="PPL",
#             country_code="US",
#             admin1_code="CA",
#             population=2,
#             alternates=[GeonameAlternate(3, long_name.lower())],
#         )
#     )
#     assert chunk.to_json_serializable() == {
#         "geonames": [
#             {
#                 "admin1_code": "AL",
#                 "alternate_names": ["waterloo"],
#                 "alternate_names_2": [
#                     {"name": "waterloo"},
#                 ],
#                 "country_code": "US",
#                 "feature_class": "P",
#                 "feature_code": "PPL",
#                 "id": 1,
#                 "latitude": "34.91814",
#                 "longitude": "-88.0642",
#                 "name": "Waterloo",
#                 "population": 200,
#             },
#             {
#                 "admin1_code": "AL",
#                 "alternate_names": ["al", "alabama"],
#                 "alternate_names_2": [
#                     {"name": "al", "iso_language": "abbr"},
#                     {"name": "alabama"},
#                 ],
#                 "country_code": "US",
#                 "feature_class": "A",
#                 "feature_code": "ADM1",
#                 "id": 2,
#                 "latitude": "32.75041",
#                 "longitude": "-86.75026",
#                 "name": "Alabama",
#                 "population": 4530315,
#             },
#             {
#                 "admin1_code": "CA",
#                 "alternate_names": [long_name.lower()],
#                 "alternate_names_2": [
#                     {"name": long_name.lower()},
#                 ],
#                 "country_code": "US",
#                 "feature_class": "P",
#                 "feature_code": "PPL",
#                 "id": 3,
#                 "latitude": "0.0",
#                 "longitude": "0.0",
#                 "name": long_name,
#                 "population": 2,
#             },
#         ],
#         "max_alternate_name_length": len(long_name),
#         "max_alternate_name_word_count": 10,
#     }
