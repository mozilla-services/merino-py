# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the wikipedia indexer filemanager module."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from requests import HTTPError
from merino.jobs.wikipedia_indexer.filemanager import FileManager, WikipediaFilemanagerError


def test_get_latest_gcs_returns_latest_blob():
    """Returns the most recent matching blob for a given language."""
    mock_client = MagicMock()
    mock_bucket = MagicMock()

    mock_blob_old = MagicMock()
    mock_blob_old.name = "frwiki-20240101-cirrussearch-content.json.gz"

    mock_blob_new = MagicMock()
    mock_blob_new.name = "frwiki-20240401-cirrussearch-content.json.gz"

    mock_bucket.list_blobs.return_value = [mock_blob_old, mock_blob_new]
    mock_client.bucket.return_value = mock_bucket

    with patch("merino.jobs.wikipedia_indexer.filemanager.Client", return_value=mock_client):
        fm = FileManager("gcs-bucket", "gcs-project", "", language="fr")
        latest_blob = fm.get_latest_gcs()

    assert latest_blob == mock_blob_new


def test_get_latest_gcs_filters_by_language():
    """Filters out blobs not matching the current language pattern."""
    mock_client = MagicMock()
    mock_bucket = MagicMock()

    fr_blob = MagicMock()
    fr_blob.name = "frwiki-20240301-cirrussearch-content.json.gz"

    en_blob = MagicMock()
    en_blob.name = "enwiki-20240301-cirrussearch-content.json.gz"

    random_blob = MagicMock()
    random_blob.name = "unrelated-file.txt"

    mock_bucket.list_blobs.return_value = [fr_blob, en_blob, random_blob]
    mock_client.bucket.return_value = mock_bucket

    with patch("merino.jobs.wikipedia_indexer.filemanager.Client", return_value=mock_client):
        fm = FileManager("gcs-bucket", "gcs-project", "", language="fr")
        result = fm.get_latest_gcs()

    # the frwiki blob should match and be returned
    assert result == fr_blob


def test_get_latest_gcs_raises_runtime_error_if_no_matches():
    """Raises RuntimeError when no blobs match the language-specific pattern."""
    mock_client = MagicMock()
    mock_bucket = MagicMock()

    en_blob = MagicMock()
    en_blob.name = "enwiki-20240301-cirrussearch-content.json.gz"

    unrelated_blob = MagicMock()
    unrelated_blob.name = "somefile.txt"

    mock_bucket.list_blobs.return_value = [en_blob, unrelated_blob]
    mock_client.bucket.return_value = mock_bucket

    with patch("merino.jobs.wikipedia_indexer.filemanager.Client", return_value=mock_client):
        fm = FileManager("gcs-bucket", "gcs-project", "", language="fr")

        with pytest.raises(RuntimeError, match="No matching dump files found"):
            fm.get_latest_gcs()


@patch("requests.get")
def test_get_latest_dump_returns_url_if_newer(mock_get):
    """Returns a full download URL if the dump is newer than the one in GCS."""
    mock_client = MagicMock()
    # HTML content with a single matching link
    html = '<a href="frwiki-20240401-cirrussearch-content.json.gz">download</a>'
    mock_get.return_value.content = html

    mock_blob = MagicMock()
    mock_blob.name = "frwiki-20240301-cirrussearch-content.json.gz"  # older GCS file

    with patch("merino.jobs.wikipedia_indexer.filemanager.Client", return_value=mock_client):
        fm = FileManager("gcs-bucket", "gcs-project", "http://mock-url/", "fr")
        result = fm.get_latest_dump(mock_blob)

    assert result == "http://mock-url/frwiki-20240401-cirrussearch-content.json.gz"


@patch("requests.get")
def test_get_latest_dump_returns_none_if_not_newer(mock_get):
    """Returns None when the latest dump in GCS is up to date or newer."""
    mock_client = MagicMock()
    # File in HTML is same date or older
    html = '<a href="frwiki-20240301-cirrussearch-content.json.gz">download</a>'
    mock_get.return_value.content = html

    mock_blob = MagicMock()
    mock_blob.name = "frwiki-20240301-cirrussearch-content.json.gz"  # same date

    with patch("merino.jobs.wikipedia_indexer.filemanager.Client", return_value=mock_client):
        fm = FileManager("gcs-bucket", "gcs-project", "http://mock-url/", "fr")
        result = fm.get_latest_dump(mock_blob)

    assert result is None


@patch("requests.get")
def test_stream_dump_to_gcs_success(mock_get):
    """Streams and writes a remote dump to GCS successfully."""
    mock_chunk = b"x" * 1024

    mock_response = MagicMock()
    mock_response.__enter__.return_value = mock_response
    mock_response.iter_content.return_value = [mock_chunk, mock_chunk]
    mock_response.headers = {"Content-Length": str(len(mock_chunk) * 2)}
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    mock_writer = MagicMock()
    mock_writer.write.side_effect = lambda chunk: len(chunk)

    mock_blob = MagicMock()
    mock_blob.open.return_value.__enter__.return_value = mock_writer

    mock_bucket = MagicMock()
    mock_bucket.blob.return_value = mock_blob

    mock_client = MagicMock()
    mock_client.bucket.return_value = mock_bucket

    with patch("merino.jobs.wikipedia_indexer.filemanager.Client", return_value=mock_client):
        fm = FileManager("gcs-bucket", "gcs-project", "http://mock-url/", "fr")
        fm._stream_dump_to_gcs("http://mock-url/frwiki-20240501-cirrussearch-content.json.gz")

    # Assertions
    mock_writer.write.assert_called()
    assert mock_writer.write.call_count == 2
    mock_blob.open.assert_called_once()
    mock_get.assert_called_once_with(
        "http://mock-url/frwiki-20240501-cirrussearch-content.json.gz", stream=True
    )


@patch("requests.get")
def test_stream_dump_to_gcs_handles_stream_failure_and_deletes_blob(mock_get):
    """Handles stream failure by deleting the partial GCS blob and raising an error."""
    mock_response = MagicMock()
    mock_response.__enter__.return_value = mock_response
    mock_response.raise_for_status.side_effect = HTTPError("Simulated HTTP error")

    mock_get.return_value = mock_response

    mock_blob = MagicMock()
    mock_blob.exists.return_value = True

    mock_bucket = MagicMock()
    mock_bucket.blob.return_value = mock_blob

    mock_client = MagicMock()
    mock_client.bucket.return_value = mock_bucket

    with patch("merino.jobs.wikipedia_indexer.filemanager.Client", return_value=mock_client):
        fm = FileManager("gcs-bucket", "gcs-project", "http://mock-url/", "fr")

        with pytest.raises(WikipediaFilemanagerError, match="Failed to stream dump to GCS"):
            fm._stream_dump_to_gcs("http://mock-url/frwiki-20240501-cirrussearch-content.json.gz")

    mock_blob.exists.assert_called_once()
    mock_blob.delete.assert_called_once()


@patch.object(FileManager, "_stream_dump_to_gcs")
@patch.object(FileManager, "get_latest_dump")
@patch.object(FileManager, "get_latest_gcs")
def test_stream_latest_dump_triggers_stream(
    mock_get_latest_gcs, mock_get_latest_dump, mock_stream
):
    """Triggers dump streaming when a newer remote dump is available."""
    mock_client = MagicMock()
    mock_blob = MagicMock()
    mock_get_latest_gcs.return_value = mock_blob
    mock_get_latest_dump.return_value = "http://mock-url/frwiki-latest.json.gz"

    with patch("merino.jobs.wikipedia_indexer.filemanager.Client", return_value=mock_client):
        fm = FileManager("gcs-bucket", "gcs-project", "http://mock-url/", "fr")
        returned_blob = fm.stream_latest_dump_to_gcs()

    mock_stream.assert_called_once_with("http://mock-url/frwiki-latest.json.gz")
    assert returned_blob == mock_blob


@patch.object(FileManager, "_stream_dump_to_gcs")
@patch.object(FileManager, "get_latest_dump")
@patch.object(FileManager, "get_latest_gcs")
def test_stream_latest_dump_skips_if_up_to_date(
    mock_get_latest_gcs, mock_get_latest_dump, mock_stream
):
    """Skips dump streaming when no newer dump is available."""
    mock_client = MagicMock()
    mock_blob = MagicMock()
    mock_get_latest_gcs.return_value = mock_blob
    mock_get_latest_dump.return_value = None  # No newer dump

    with patch("merino.jobs.wikipedia_indexer.filemanager.Client", return_value=mock_client):
        fm = FileManager("gcs-bucket", "gcs-project", "http://mock-url/", "fr")
        returned_blob = fm.stream_latest_dump_to_gcs()

    mock_stream.assert_not_called()
    assert returned_blob == mock_blob


def test_parse_date_returns_correct_datetime():
    """Parses and returns the correct datetime from a valid filename."""
    mock_client = MagicMock()
    with patch("merino.jobs.wikipedia_indexer.filemanager.Client", return_value=mock_client):
        fm = FileManager("gcs-bucket", "gcs-project", "http://mock-url/", "fr")

        filename = "frwiki-20240501-cirrussearch-content.json.gz"
        result = fm._parse_date(filename)

        assert isinstance(result, datetime)
        assert result == datetime(2024, 5, 1)


def test_parse_date_returns_default_on_invalid_filename():
    """Returns the default fallback datetime when the filename is invalid."""
    mock_client = MagicMock()
    with patch("merino.jobs.wikipedia_indexer.filemanager.Client", return_value=mock_client):
        fm = FileManager("gcs-bucket", "gcs-project", "http://mock-url/", "fr")

        filename = "invalid-file-name.txt"
        result = fm._parse_date(filename)

        assert result == datetime(1, 1, 1)


def test_filemanager_rejects_invalid_language():
    """Raises ValueError if FileManager is initialized with an unsupported language."""
    with pytest.raises(ValueError, match="Unsupported language 'es'"):
        FileManager("gcs-bucket", "gcs-project", "http://mock-url", language="es")
