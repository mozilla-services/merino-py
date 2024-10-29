# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for __init__.py module."""

from typing import Any

from merino.jobs.geonames_uploader.downloader import (
    DownloadMetrics,
    DownloadState,
    Geoname,
)
from merino.jobs.geonames_uploader import GeonamesChunk, upload


def do_uploader_test(
    mocker,
    geonames: list[Geoname],
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

    # Do the upload.
    upload_kwargs: dict[str, Any] = {
        "auth": "auth",
        "bucket": "bucket",
        "chunk_size": 99,
        "collection": "collection",
        "dry_run": False,
        "record_type": "geonames",
        "server": "server",
    }
    downloader_kwargs: dict[str, Any] = {
        "alternates_path": "/alternates/{country_code}.zip",
        "city_alternates_iso_languages": ["en", "iata"],
        "base_url": "https://localhost",
        "country_code": "US",
        "geonames_path": "/{country_code}.zip",
        "population_threshold": 12345,
        "region_alternates_iso_languages": ["abbr"],
    }

    upload(
        **upload_kwargs,
        **downloader_kwargs,
        keep_existing_records=keep_existing_records,
    )

    # Check geonames downloader calls.
    mock_downloader_ctor.assert_called_once_with(**downloader_kwargs)
    mock_downloader.download.assert_called_once()

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
        geonames=[
            Geoname(
                id="1",
                name="Waterloo",
                latitude="34.91814",
                longitude="-88.0642",
                feature_class="P",
                feature_code="PPL",
                country_code="US",
                admin1_code="AL",
                population=200,
                alternate_names=set(["waterloo"]),
            ),
        ],
        keep_existing_records=True,
    )


def test_delete_and_upload(mocker):
    """upload(keep_existing_records=False)"""
    do_uploader_test(
        mocker=mocker,
        geonames=[
            Geoname(
                id="1",
                name="Waterloo",
                latitude="34.91814",
                longitude="-88.0642",
                feature_class="P",
                feature_code="PPL",
                country_code="US",
                admin1_code="AL",
                population=200,
                alternate_names=set(["waterloo"]),
            ),
        ],
        keep_existing_records=False,
    )
