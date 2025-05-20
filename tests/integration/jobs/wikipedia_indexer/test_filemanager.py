"""FileManager tests"""

import re
from datetime import datetime as dt
from unittest.mock import MagicMock, patch

import pytest
from google.cloud.storage import Blob

from merino.jobs.wikipedia_indexer.filemanager import (
    DirectoryParser,
    FileManager,
    WikipediaFilemanagerError,
)


@pytest.fixture
def mock_gcs_client(mocker):
    """Return a mock GCS Client instance"""
    return mocker.patch("merino.jobs.wikipedia_indexer.filemanager.Client").return_value


@pytest.fixture
def mock_wiki_http_response():
    """Fixture to create a mock HTTP response."""

    def _mock_response(chunks, status_code=200):
        mock_resp = MagicMock()
        mock_resp.iter_content.return_value = chunks
        mock_resp.headers = {"Content-Length": str(sum(len(c) for c in chunks))}
        mock_resp.status_code = status_code
        mock_resp.raise_for_status.return_value = (
            None if status_code == 200 else Exception("HTTP Error")
        )
        return mock_resp

    return _mock_response


def test_directory_parser():
    """Test directory parser logic"""
    html_directory = """
    <a href="some_file.json" />
    <br />
    <a href="123.json" />
    <link src="something_else" />
    <a href="456.json" />
    """

    parser = DirectoryParser(re.compile("\\d+.json"))
    parser.feed(html_directory)

    assert len(parser.file_paths) == 2
    assert parser.file_paths[0] == "123.json"


@pytest.mark.usefixtures("mock_gcs_client")
@pytest.mark.parametrize(
    ["file_name", "expected_datetime"],
    [
        ("just-some-file.json", dt(1, 1, 1)),
        ("enwiki-20220101-cirrussearch-content.json.gz", dt(2022, 1, 1)),
        ("enwiki-19890101-cirrussearch-content.json.gz", dt(1989, 1, 1)),
        ("foo/bar/enwiki-19890101-cirrussearch-content.json.gz", dt(1989, 1, 1)),
        ("enwiki-20190132-cirrussearch-content.json.gz", dt(1, 1, 1)),
        ("enwiki-1234-cirrussearch-content.json.gz", dt(1, 1, 1)),
    ],
)
def test_parse_date(file_name, expected_datetime):
    """Test parse date regexp properly converts to a valid or sentinel datetime"""
    file_manager = FileManager("foo/bar", "a-project", "http://foo/", "en")

    parsed_date = file_manager._parse_date(file_name)

    assert parsed_date == expected_datetime


@pytest.mark.usefixtures("mock_gcs_client")
@pytest.mark.parametrize(
    ["gcs_bucket", "expected_bucket", "expected_prefix"],
    [
        ("foo", "foo", ""),
        ("foo/bar", "foo", "bar"),
        ("foo/bar/baz", "foo", "bar/baz"),
    ],
)
def test_parse_gcs_bucket(gcs_bucket, expected_bucket, expected_prefix):
    """Test gcs bucket path parsing"""
    file_manager = FileManager(gcs_bucket, "a-project", "http://foo/", "en")

    assert file_manager.gcs_bucket == expected_bucket
    assert file_manager.object_prefix == expected_prefix


@pytest.mark.usefixtures("mock_gcs_client")
@pytest.mark.parametrize(
    ["file_date", "gcs_date", "expected"],
    [
        (
            "20220101",
            "20210101",
            "http://test.com/enwiki-20220101-cirrussearch-content.json.gz",
        ),
        (
            "20210101",
            "20220101",
            None,
        ),
    ],
)
def test_get_latest_dump(requests_mock, file_date, gcs_date, expected):
    """Test directory parser and date comparisons of get_latest_dump"""
    base_url = "http://test.com"
    file_name = f"enwiki-{file_date}-cirrussearch-content.json.gz"
    latest_gcs = Blob(f"bar/enwiki-{gcs_date}-cirrussearch-content.json.gz", "foo")
    html_directory = f"<a href='{file_name}' />"
    requests_mock.get(base_url, text=html_directory)  # nosec

    file_manager = FileManager("foo/bar", "a-project", base_url, "en")

    latest_dump_url = file_manager.get_latest_dump(latest_gcs)

    assert latest_dump_url == expected


def test_get_latest_gcs(mock_gcs_client):
    """Test sorting logic for get_latest_gcs method"""
    blob1 = Blob("enwiki-20220101-cirrussearch-content.json.gz", "foo")
    blob2 = Blob("enwiki-20210101-cirrussearch-content.json.gz", "foo")

    mock_bucket = mock_gcs_client.bucket.return_value
    mock_bucket.list_blobs.return_value = [blob1, blob2]

    file_manager = FileManager("foo/bar", "a-project", "", "en")
    latest_gcs = file_manager.get_latest_gcs()

    assert latest_gcs == blob1


@patch("requests.get")
def test_stream_dump_to_gcs_success(mock_requests, mock_gcs_client, mock_wiki_http_response):
    """Test successful streaming of wiki dump to GCS"""
    base_url = "http://test.com"
    dump_url = "http://test.com/enwiki-20220101-cirrussearch-content.json.gz"

    chunks = [b"chunk1", b"chunk2", b"chunk3"]

    mock_resp = mock_wiki_http_response(chunks)
    mock_requests.return_value.__enter__.return_value = mock_resp

    mock_bucket = MagicMock()
    mock_gcs_client.bucket.return_value = mock_bucket

    mock_blob = MagicMock()
    mock_blob.name = "wiki-upload"
    mock_bucket.blob.return_value = mock_blob

    mock_blob_writer = MagicMock()
    mock_blob.open.return_value.__enter__.return_value = mock_blob_writer
    mock_blob.open.return_value.__exit__.return_value = None

    file_manager = FileManager(mock_bucket, "a-project", base_url, "en")
    file_manager._stream_dump_to_gcs(dump_url)

    mock_blob.open.assert_called_once_with("wb")

    mock_blob_writer.write.assert_any_call(b"chunk1")
    mock_blob_writer.write.assert_any_call(b"chunk2")
    mock_blob_writer.write.assert_any_call(b"chunk3")

    assert mock_blob_writer.write.call_count == len(chunks)


@patch("requests.get")
def test_stream_dump_to_gcs_blob_deletion(mock_requests, mock_gcs_client, mock_wiki_http_response):
    """Test deletion of partial upload on unsuccessful streaming of wiki dump to GCS"""
    base_url = "http://test.com"
    dump_url = "http://test.com/enwiki-20220101-cirrussearch-content.json.gz"

    chunks = [b"chunk1", b"chunk2", b"chunk3"]
    mock_resp = mock_wiki_http_response(chunks)
    mock_requests.return_value.__enter__.return_value = mock_resp

    mock_bucket = MagicMock()
    mock_gcs_client.bucket.return_value = mock_bucket

    mock_blob = MagicMock()
    mock_blob.name = "wiki-upload"
    mock_bucket.blob.return_value = mock_blob

    mock_blob.exists.return_value = True
    mock_blob.delete.return_value = None

    mock_blob_writer = MagicMock()
    mock_blob.open.return_value.__enter__.return_value = mock_blob_writer

    # raise an exception during streaming
    mock_blob_writer.write.side_effect = Exception("failed to write chunk")

    file_manager = FileManager(mock_bucket, "a-project", base_url, "en")

    with pytest.raises(WikipediaFilemanagerError, match="Failed to stream dump to GCS"):
        file_manager._stream_dump_to_gcs(dump_url)

    mock_blob.exists.assert_called_once()
    mock_blob.delete.assert_called_once()
