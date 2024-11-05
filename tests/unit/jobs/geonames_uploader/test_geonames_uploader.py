# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for __init__.py module."""

from itertools import chain
from typing import Any

from merino.jobs.geonames_uploader.downloader import (
    DownloadMetrics,
    DownloadState,
    Geoname,
    GeonameAlternate,
)
from merino.jobs.geonames_uploader import GeonamesChunk, upload


def do_uploader_test(
    mocker,
    geonames: list[Geoname],
    country_codes: list[str],
    keep_existing_records: bool = True,
) -> None:
    """Perform a geonames upload test."""
    # Mock the geonames downloader.
    mock_downloader_ctor = mocker.patch("merino.jobs.geonames_uploader.GeonamesDownloader")
    mock_downloader = mock_downloader_ctor.return_value
    mock_downloader.download.return_value = DownloadState(
        geonames=geonames,
        geonames_by_id={g.id: g for g in geonames},
        metrics=DownloadMetrics(
            excluded_geonames_count=0,
            included_alternates_count=0,
        ),
    )

    # Mock the chunked uploader.
    mock_chunked_uploader_ctor = mocker.patch(
        "merino.jobs.geonames_uploader.ChunkedRemoteSettingsUploader"
    )
    mock_chunked_uploader = mock_chunked_uploader_ctor.return_value.__enter__.return_value

    # kwargs common to `upload()` and the chunked uploader.
    upload_kwargs: dict[str, Any] = {
        "auth": "auth",
        "bucket": "bucket",
        "chunk_size": 99,
        "collection": "collection",
        "dry_run": False,
        "record_type": "geonames",
        "server": "server",
    }

    # kwargs common to `upload()` and `GeonamesDownloader`.
    common_kwargs: dict[str, Any] = {
        "alternates_path": "/alternates/{country_code}.zip",
        "city_alternates_iso_languages": ["en", "iata"],
        "base_url": "https://localhost",
        "geonames_path": "/{country_code}.zip",
        "population_threshold": 12345,
        "region_alternates_iso_languages": ["abbr"],
    }

    # Do the upload.
    upload(
        **upload_kwargs,
        **common_kwargs,
        country_codes=country_codes,
        keep_existing_records=keep_existing_records,
    )

    # Check geonames downloader calls.
    mock_downloader_ctor.assert_has_calls(
        list(
            chain.from_iterable(
                (mocker.call(country_code=c, **common_kwargs), mocker.call().download())
                for c in country_codes
            )
        )
    )
    mock_downloader.download.assert_has_calls([mocker.call()] * len(country_codes))

    # Check chunked uploader calls.
    mock_chunked_uploader_ctor.assert_called_once_with(
        **upload_kwargs,
        allow_delete=True,
        chunk_cls=GeonamesChunk,
        total_item_count=len(geonames),
    )

    if not keep_existing_records:
        mock_chunked_uploader.delete_records.assert_called_once()
    else:
        mock_chunked_uploader.delete_records.assert_not_called()

    mock_chunked_uploader.add_item.assert_has_calls([*map(mocker.call, geonames)])


def test_upload_without_deleting(mocker):
    """upload(keep_existing_records=True)"""
    do_uploader_test(
        mocker=mocker,
        country_codes=["US"],
        keep_existing_records=True,
        geonames=[
            Geoname(
                id=1,
                name="Waterloo",
                latitude="34.91814",
                longitude="-88.0642",
                feature_class="P",
                feature_code="PPL",
                country_code="US",
                admin1_code="AL",
                population=200,
                alternates=[GeonameAlternate(1, "waterloo")],
            ),
        ],
    )


def test_delete_and_upload(mocker):
    """upload(keep_existing_records=False)"""
    do_uploader_test(
        mocker=mocker,
        country_codes=["US"],
        keep_existing_records=False,
        geonames=[
            Geoname(
                id=1,
                name="Waterloo",
                latitude="34.91814",
                longitude="-88.0642",
                feature_class="P",
                feature_code="PPL",
                country_code="US",
                admin1_code="AL",
                population=200,
                alternates=[GeonameAlternate(1, "waterloo")],
            ),
        ],
    )


def test_upload_multiple_countries(mocker):
    """upload() with multiple countries"""
    do_uploader_test(
        mocker=mocker,
        country_codes=["US", "CA"],
        keep_existing_records=True,
        geonames=[
            Geoname(
                id=1,
                name="Waterloo",
                latitude="34.91814",
                longitude="-88.0642",
                feature_class="P",
                feature_code="PPL",
                country_code="US",
                admin1_code="AL",
                population=200,
                alternates=[GeonameAlternate(1, "waterloo")],
            ),
        ],
    )


def test_to_json_serializable():
    """Test GeonamesChunk.to_json_serializable()"""
    chunk = GeonamesChunk(0)
    chunk.add_item(
        Geoname(
            id=1,
            name="Waterloo",
            latitude="34.91814",
            longitude="-88.0642",
            feature_class="P",
            feature_code="PPL",
            country_code="US",
            admin1_code="AL",
            population=200,
            alternates=[GeonameAlternate(1, "waterloo")],
        )
    )
    chunk.add_item(
        Geoname(
            id=2,
            name="Alabama",
            latitude="32.75041",
            longitude="-86.75026",
            feature_class="A",
            feature_code="ADM1",
            country_code="US",
            admin1_code="AL",
            population=4530315,
            alternates=[GeonameAlternate(2, "alabama"), GeonameAlternate(2, "al", "abbr")],
        )
    )
    # Add a geoname with a long name and many words *last* to make sure
    # `max_alternate_name_length` and `max_alternate_name_word_count` are
    # updated correctly.
    long_name = "A very long name with a lot of different words"
    chunk.add_item(
        Geoname(
            id=3,
            name=long_name,
            latitude="0.0",
            longitude="0.0",
            feature_class="P",
            feature_code="PPL",
            country_code="US",
            admin1_code="CA",
            population=2,
            alternates=[GeonameAlternate(3, long_name.lower())],
        )
    )
    assert chunk.to_json_serializable() == {
        "geonames": [
            {
                "admin1_code": "AL",
                "alternate_names": ["waterloo"],
                "alternate_names_2": [
                    {"name": "waterloo"},
                ],
                "country_code": "US",
                "feature_class": "P",
                "feature_code": "PPL",
                "id": 1,
                "latitude": "34.91814",
                "longitude": "-88.0642",
                "name": "Waterloo",
                "population": 200,
            },
            {
                "admin1_code": "AL",
                "alternate_names": ["al", "alabama"],
                "alternate_names_2": [
                    {"name": "al", "iso_language": "abbr"},
                    {"name": "alabama"},
                ],
                "country_code": "US",
                "feature_class": "A",
                "feature_code": "ADM1",
                "id": 2,
                "latitude": "32.75041",
                "longitude": "-86.75026",
                "name": "Alabama",
                "population": 4530315,
            },
            {
                "admin1_code": "CA",
                "alternate_names": [long_name.lower()],
                "alternate_names_2": [
                    {"name": long_name.lower()},
                ],
                "country_code": "US",
                "feature_class": "P",
                "feature_code": "PPL",
                "id": 3,
                "latitude": "0.0",
                "longitude": "0.0",
                "name": long_name,
                "population": 2,
            },
        ],
        "max_alternate_name_length": len(long_name),
        "max_alternate_name_word_count": 10,
    }
