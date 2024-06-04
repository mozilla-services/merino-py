"""Test utils for the csv_rs_uploader module"""
import asyncio
import csv
import io
from typing import Any, Callable

import pytest

from merino.jobs.csv_rs_uploader import _upload_file_object, upload


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
    model_name: str,
    model_package: str,
    upload_callable: Callable[[dict[str, Any]], None],
    delete_existing_records: bool,
    record_type: str,
    score: float,
    expected_suggestions: list[dict[str, Any]],
    expected_record_type: str,
) -> None:
    """Helper-method for `do_csv_test()`"""
    # Mock the chunked uploader.
    mock_chunked_uploader_ctor = mocker.patch(
        "merino.jobs.csv_rs_uploader.ChunkedRemoteSettingsSuggestionUploader"
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
        "record_type": record_type,
        "server": "server",
    }
    upload_callable(
        {
            **common_kwargs,
            "delete_existing_records": delete_existing_records,
            "score": score,
            "model_name": model_name,
            "model_package": model_package,
        }
    )

    # Check calls.
    del common_kwargs["record_type"]
    mock_chunked_uploader_ctor.assert_called_once_with(
        **common_kwargs,
        record_type=expected_record_type,
        suggestion_score_fallback=score,
        total_data_count=len(expected_suggestions),
    )

    if delete_existing_records:
        mock_chunked_uploader.delete_records.assert_called_once()
    else:
        mock_chunked_uploader.delete_records.assert_not_called()

    mock_chunked_uploader.add_suggestion.assert_has_calls(
        [*map(mocker.call, expected_suggestions)]
    )


def do_csv_test(
    mocker,
    model_name: str,
    expected_suggestions: list[dict[str, Any]],
    csv_path: str | None = None,
    csv_rows: list[dict[str, str]] | None = None,
    delete_existing_records: bool = False,
    record_type: str = "record_type",
    expected_record_type: str = "record_type",
    score: float = 0.99,
    model_package: str = "merino.jobs.csv_rs_uploader",
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
        model_name=model_name,
        model_package=model_package,
        upload_callable=uploader,
        delete_existing_records=delete_existing_records,
        record_type=record_type,
        score=score,
        expected_suggestions=expected_suggestions,
        expected_record_type=expected_record_type,
    )

    if file_object:
        file_object.close()


def do_error_test(
    mocker,
    model_name: str,
    csv_rows: list[dict[str, str]],
    expected_error: type,
    model_package: str = "merino.jobs.csv_rs_uploader",
) -> None:
    """Perform an upload test that is expected to raise an error."""
    file_object = _make_csv_file_object(csv_rows)
    with pytest.raises(expected_error):
        asyncio.run(
            _upload_file_object(
                auth="auth",
                bucket="bucket",
                chunk_size=99,
                collection="collection",
                delete_existing_records=False,
                dry_run=False,
                file_object=file_object,
                model_name=model_name,
                model_package=model_package,
                record_type="record_type",
                score=0.2,
                server="server",
            )
        )
    file_object.close()
