# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for __init__.py module."""

#XXXadw all geoname populations below requested threshold

from copy import deepcopy
import json
from itertools import chain
from typing import Any

from merino.jobs.geonames_uploader.downloader import (
    DownloadMetrics,
    DownloadState,
    Geoname,
)
from merino.jobs.geonames_uploader import upload


# Waterloo, AL
GEONAME_WATERLOO_AL = Geoname(
    id=4096497,
    name="Waterloo",
    latitude="34.91814",
    longitude="-88.0642",
    feature_class="P",
    feature_code="PPL",
    country_code="US",
    admin1_code="AL",
    admin2_code="077",
    population=200,
)
JSONABLE_WATERLOO_AL = {
    "id": 4096497,
    "name": "Waterloo",
    "latitude": "34.91814",
    "longitude": "-88.0642",
    "feature_class": "P",
    "feature_code": "PPL",
    "country_code": "US",
    "population": 200,
    "admin1_code": "AL",
    "admin2_code": "077",
}

def with_alternates(geoname: Geoname, alts: dict[str, list[str]]) -> Geoname:
    g = deepcopy(geoname)
    g.alternates_by_iso_language = alts
    return g


class ExpectedRsUpload:
    lower_threshold: int
    upper_threshold: int | None
    record: dict[str, Any]
    attachment_jsonable: dict[str, Any]

    def __init__(
        self,
        lower_threshold: int,
        upper_threshold: int | None,
        record: dict[str, Any],
        attachment_jsonable: dict[str, Any],
    ):
        self.lower_threshold = lower_threshold
        self.upper_threshold = lower_threshold
        self.record = record
        self.attachment_jsonable = attachment_jsonable


def do_uploader_test(
    mocker,
    geonames: list[Geoname],
    geoname_countries: list[str],
    population_thresholds: list[int],
    client_countries: list[str],
    client_locales: list[str],
    expected_rs_uploads: list[ExpectedRsUpload],
    geonames_record_type: str = "geonames-2",
    keep_existing_records: bool = True,
) -> None:
    """Perform a geonames upload test."""
    min_threshold = min(population_thresholds)

    # Mock the geonames downloader.
    mock_downloader_ctor = mocker.patch("merino.jobs.geonames_uploader.GeonamesDownloader")
    mock_downloader = mock_downloader_ctor.return_value
    mock_downloader.download.return_value = DownloadState(
        geonames_by_id={g.id: g for g in geonames if min_threshold <= g.population},
        metrics=DownloadMetrics(
            excluded_geonames_count=0,
            included_alternates_count=0,
        ),
    )

    # Mock the RS uploader.
    mock_rs_uploader_ctor = mocker.patch(
        "merino.jobs.geonames_uploader.RemoteSettingsUploader"
    )
    mock_rs_uploader = mock_rs_uploader_ctor.return_value
    mock_rs_uploader.upload.return_value = None

    # kwargs common to the job's `upload()` and the RS uploader ctor.
    common_job_and_rs_uploader_kwargs: dict[str, Any] = {
        "auth": "auth",
        "bucket": "bucket",
        "collection": "collection",
        "dry_run": False,
        "server": "server",
    }

    # kwargs common to the job's `upload()` and the `GeonamesDownloader` ctor.
    common_job_and_geonames_downloader_kwargs: dict[str, Any] = {
        "alternates_path": "/alternates/{country_code}.zip",
        "city_alternates_iso_languages": ["en", "iata"],
        "base_url": "https://localhost",
        "geonames_path": "/{country_code}.zip",
        "admin_alternates_iso_languages": ["abbr"],
    }

    # Call the job's `upload()`.
    upload(
        **common_job_and_rs_uploader_kwargs,
        **common_job_and_geonames_downloader_kwargs,
        geonames_record_type=geonames_record_type,
        population_thresholds=population_thresholds,
        client_countries=client_countries,
        client_locales=client_locales,
        geoname_countries=geoname_countries,
        keep_existing_records=keep_existing_records,
    )

    # Check the `GeonamesDownloader` ctor calls.
    mock_downloader_ctor.assert_has_calls(
        list(
            chain.from_iterable(
                (
                    mocker.call(
                        country_code=c,
                        population_threshold=min(population_thresholds),
                        **common_job_and_geonames_downloader_kwargs,
                    ),
                    mocker.call().download()
                )
                for c in geoname_countries
            )
        )
    )
    mock_downloader.download.assert_has_calls([mocker.call()] * len(geoname_countries))

    # Check RS uploader ctor calls.
    mock_rs_uploader_ctor.assert_called_once_with(
        **common_job_and_rs_uploader_kwargs,
    )

    # Check RS uploader `upload()` calls.
    mock_rs_uploader.upload.assert_has_calls(
        list(
            chain.from_iterable(
                (
                    mocker.call(
                        record=u.record,
                        attachment_json=json.dumps(u.attachment_jsonable),
                    ),
                )
                for u in expected_rs_uploads
            )
        )
    )

    #XXXadw check record filter expression

#     if not keep_existing_records:
#         mock_rs_uploader.delete_records.assert_called_once()
#     else:
#         mock_rs_uploader.delete_records.assert_not_called()




def test_upload_without_deleting(mocker):
    """upload(keep_existing_records=True)"""
    do_uploader_test(
        mocker=mocker,
        geoname_countries=["US"],
        client_countries=["US"],
        client_locales=["en-US"],
        population_thresholds=[1],
        keep_existing_records=True,
        geonames=[
            with_alternates(GEONAME_WATERLOO_AL, {
                "en": ["Waterloo"],
            }),
        ],
        expected_rs_uploads=[
            ExpectedRsUpload(
                lower_threshold=1,
                upper_threshold=None,
                record={
                    "id": "geonames-US-1",
                    "type": "geonames-2",
                    "filter_expression": "env.country in ['US'] && env.locale in ['en-US']",
                },
                attachment_jsonable=[JSONABLE_WATERLOO_AL],
            ),
        ],
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
