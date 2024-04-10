"""Test utils for the relevancy csv_rs_uploader module"""
import asyncio
import csv
import io
from typing import Any, Callable

import pytest

from merino.jobs.relevancy_uploader import _upload_file_object, upload


def _make_csv_file_object(csv_rows: list[dict[str, str]]) -> io.TextIOWrapper:
    """Return a StringIO that encodes the given CSV rows."""
    f = io.StringIO()
    csv_writer = csv.DictWriter(f, fieldnames=[*csv_rows[0].keys()])
    csv_writer.writeheader()
    for row in csv_rows:
        csv_writer.writerow(row)
    f.seek(0)
    return f


def _do_csv_test(
    mocker,
    upload_callable: Callable[[dict[str, Any]], None],
    delete_existing_records: bool,
    expected_data: list[dict[str, Any]],
) -> None:
    """Helper-method for `do_csv_test()`"""
    # Mock the chunked uploader.
    mock_chunked_uploader_ctor = mocker.patch(
        "merino.jobs.relevancy_uploader.ChunkedRemoteSettingsRelevancyUploader"
    )
    mock_chunked_uploader = (
        mock_chunked_uploader_ctor.return_value.__enter__.return_value
    )

    # Do the upload.
    common_kwargs: dict[str, Any] = {
        "auth": "auth",
        "bucket": "bucket",
        "chunk_size": 99,
        "collection": "collection",
        "dry_run": False,
        "server": "server",
    }
    upload_callable(
        {
            **common_kwargs,
            "delete_existing_records": delete_existing_records,
        }
    )

    mock_chunked_uploader_ctor.assert_called_once_with(
        **common_kwargs,
        record_type="category_to_domains",
        suggestion_score_fallback=0,
        total_data_count=len(expected_data),
        category_name="Sports",
        category_code=16
    )

    if delete_existing_records:
        mock_chunked_uploader.delete_records.assert_called_once()
    else:
        mock_chunked_uploader.delete_records.assert_not_called()

    mock_chunked_uploader.add_relevancy_data.assert_has_calls(
        [*map(mocker.call, expected_data)]
    )


def do_csv_test(
    mocker,
    expected_suggestions: list[dict[str, Any]],
    csv_path: str | None = None,
    csv_rows: list[dict[str, str]] | None = None,
    delete_existing_records: bool = False,
) -> None:
    """Perform an upload test that is expected to succeed."""
    file_object = None
    if csv_rows:
        file_object = _make_csv_file_object(csv_rows)

    def uploader(kwargs):
        if csv_rows:
            asyncio.run(_upload_file_object(**kwargs, file_object=file_object))
        else:
            upload(**kwargs, csv_path=csv_path)

    _do_csv_test(
        mocker=mocker,
        upload_callable=uploader,
        delete_existing_records=delete_existing_records,
        expected_data=expected_suggestions,
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
    with pytest.raises(expected_error):
        asyncio.run(
            _upload_file_object(
                auth="auth:auth",
                bucket="bucket",
                chunk_size=99,
                collection="collection",
                delete_existing_records=False,
                dry_run=False,
                file_object=file_object,
                server="server",
            )
        )
    file_object.close()
