"""Test utils for the relevancy csv_rs_uploader module"""

import asyncio
import csv
import io
from typing import cast, Any, Callable

import pytest

from merino.jobs.relevancy_uploader import _upload_file_object, upload


def _make_csv_file_object(csv_rows: list[dict[str, str]]) -> io.StringIO:
    """Return a StringIO that encodes the given CSV rows."""
    f = io.StringIO()
    csv_writer = csv.DictWriter(f, fieldnames=[*csv_rows[0].keys()])
    csv_writer.writeheader()
    for row in csv_rows:
        csv_writer.writerow(row)
    f.seek(0)
    return f


def _mock_categories_mapping() -> dict:
    return {
        "sports.com": {"sports": 0.8},
        "sportsnnews.com": {"sports": 0.7, "news": 0.6},
        "inconclusive.com": {"inconclusive": -1},
    }


def _do_csv_test(
    mocker,
    upload_callable: Callable[[dict[str, Any]], None],
    keep_existing_records: bool,
    primary_category_data: list[dict[str, Any]],
    secondary_category_data: list[dict[str, Any]] = [],
    inconclusive_category_data: list[dict[str, Any]] = [],
    version: int = 1,
) -> None:
    """Helper-method for `do_csv_test()`"""
    # Mock the chunked uploader.
    mock_chunked_uploader_ctor = mocker.patch(
        "merino.jobs.relevancy_uploader.ChunkedRemoteSettingsRelevancyUploader"
    )
    mock_chunked_uploader = mock_chunked_uploader_ctor.return_value.__enter__.return_value

    # Mock categories mapping.
    mock_categories_mapping_patch = mocker.patch(
        "merino.jobs.relevancy_uploader._read_categories_data"
    )
    mock_categories_mapping_patch.return_value = _mock_categories_mapping()

    # Do the upload.
    common_kwargs: dict[str, Any] = {
        "auth": "auth",
        "bucket": "bucket",
        "chunk_size": 99,
        "collection": "collection",
        "dry_run": False,
        "server": "server",
        "version": version,
    }
    upload_callable(
        {
            **common_kwargs,
            "keep_existing_records": keep_existing_records,
        }
    )

    mock_chunked_uploader_ctor.assert_any_call(
        **common_kwargs,
        record_type="category_to_domains",
        category_name="",
        category_code=0,
    )

    mock_chunked_uploader_ctor.assert_any_call(
        **common_kwargs,
        record_type="category_to_domains",
        total_item_count=len(primary_category_data),
        category_name="Sports",
        category_code=17,
    )

    mock_chunked_uploader_ctor.assert_any_call(
        **common_kwargs,
        record_type="category_to_domains",
        total_item_count=len(secondary_category_data),
        category_name="News",
        category_code=14,
    )

    mock_chunked_uploader_ctor.assert_any_call(
        **common_kwargs,
        record_type="category_to_domains",
        total_item_count=len(inconclusive_category_data),
        category_name="Inconclusive",
        category_code=0,
    )

    if not keep_existing_records and version == 1:
        mock_chunked_uploader.delete_records.assert_called_once()
    else:
        mock_chunked_uploader.delete_records.assert_not_called()

    mock_chunked_uploader.add_item.assert_has_calls(
        [
            *map(
                mocker.call,
                [*primary_category_data, *secondary_category_data, *inconclusive_category_data],
            )
        ],
        any_order=True,
    )


def do_csv_test(
    mocker,
    primary_category_data: list[dict[str, Any]],
    secondary_category_data: list[dict[str, Any]],
    inconclusive_category_data: list[dict[str, Any]],
    csv_path: str | None = None,
    csv_rows: list[dict[str, str]] | None = None,
    keep_existing_records: bool = False,
    version: int = 1,
) -> None:
    """Perform an upload test that is expected to succeed."""
    file_object = None
    if csv_rows:
        file_object = _make_csv_file_object(csv_rows)

    def uploader(kwargs):
        if csv_rows:
            asyncio.run(
                _upload_file_object(**kwargs, file_object=cast(io.TextIOWrapper, file_object))
            )
        else:
            upload(**kwargs, csv_path=csv_path)

    _do_csv_test(
        mocker=mocker,
        upload_callable=uploader,
        keep_existing_records=keep_existing_records,
        primary_category_data=primary_category_data,
        secondary_category_data=secondary_category_data,
        inconclusive_category_data=inconclusive_category_data,
        version=version,
    )

    if file_object:
        file_object.close()


def do_error_test(
    mocker,
    csv_rows: list[dict[str, str]],
    expected_error: type,
) -> None:
    """Perform an upload test that is expected to raise an error."""
    file_object = _make_csv_file_object(csv_rows)

    # Mock categories mapping.
    mock_categories_mapping_patch = mocker.patch(
        "merino.jobs.relevancy_uploader._read_categories_data"
    )
    mock_categories_mapping_patch.return_value = _mock_categories_mapping()

    with pytest.raises(expected_error):
        asyncio.run(
            _upload_file_object(
                auth="auth:auth",
                bucket="bucket",
                chunk_size=99,
                collection="collection",
                keep_existing_records=True,
                dry_run=False,
                file_object=cast(io.TextIOWrapper, file_object),
                server="server",
                categories_path="test/mapping.json",
                version=1,
            )
        )
    file_object.close()
