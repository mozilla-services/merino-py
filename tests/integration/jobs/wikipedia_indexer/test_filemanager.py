"""FileManager tests"""

from datetime import datetime as dt
from unittest.mock import MagicMock, patch

import pytest
from google.cloud.storage import Blob

from merino.jobs.wikipedia_indexer.filemanager import (
    DirectoryParser,
    FileManager,
    WikipediaFilemanagerError,
)

BASE_URL = "http://test.com/"


def _index_url(date: str, language: str = "en") -> str:
    """Build the URL of a language's content index within a dated snapshot."""
    return f"{BASE_URL}{date}/index_name={language}wiki_content/"


def _links(hrefs: list[str]) -> str:
    """Render a directory listing for the given hrefs."""
    return "".join(f"<a href='{href}'>{href}</a>" for href in hrefs)


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

    parser = DirectoryParser()
    parser.feed(html_directory)

    # Every anchor href is collected; non-anchor tags are ignored.
    assert parser.file_paths == ["some_file.json", "123.json", "456.json"]


@pytest.mark.usefixtures("mock_gcs_client")
@pytest.mark.parametrize(
    ["file_name", "expected_datetime"],
    [
        ("just-some-file.json", dt(1, 1, 1)),
        ("enwiki-20220101-cirrussearch-content.json.bz2", dt(2022, 1, 1)),
        ("enwiki-19890101-cirrussearch-content.json.bz2", dt(1989, 1, 1)),
        ("foo/bar/enwiki-19890101-cirrussearch-content.json.bz2", dt(1989, 1, 1)),
        ("enwiki-20190132-cirrussearch-content.json.bz2", dt(1, 1, 1)),
        ("enwiki-1234-cirrussearch-content.json.bz2", dt(1, 1, 1)),
        # The deprecated gzip layout is no longer recognized.
        ("enwiki-20220101-cirrussearch-content.json.gz", dt(1, 1, 1)),
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
    ["snapshot_date", "gcs_date", "expected_shard_count"],
    [
        ("20220101", "20210101", 3),
        ("20210101", "20220101", 0),
    ],
    ids=["snapshot_is_newer", "snapshot_is_older"],
)
def test_get_latest_dump_shards(requests_mock, snapshot_date, gcs_date, expected_shard_count):
    """Test snapshot traversal and date comparisons of get_latest_dump_shards"""
    shard_names = [f"enwiki_content-{snapshot_date}-{i:05d}.json.bz2" for i in range(3)]
    latest_gcs = Blob(f"bar/enwiki-{gcs_date}-cirrussearch-content.json.bz2", "foo")

    requests_mock.get(BASE_URL, text=_links([f"{snapshot_date}/"]))  # nosec
    requests_mock.get(  # nosec
        _index_url(snapshot_date), text=_links([*shard_names, "_SUCCESS"])
    )

    file_manager = FileManager("foo/bar", "a-project", BASE_URL, "en")

    shard_urls = file_manager.get_latest_dump_shards(latest_gcs)

    assert len(shard_urls) == expected_shard_count
    assert shard_urls == [
        f"{_index_url(snapshot_date)}{name}" for name in shard_names[:expected_shard_count]
    ]


@pytest.mark.usefixtures("mock_gcs_client")
def test_get_latest_dump_shards_requires_success_marker(requests_mock):
    """Skip a snapshot whose shards are published but not yet marked complete."""
    requests_mock.get(BASE_URL, text=_links(["20220101/"]))  # nosec
    requests_mock.get(  # nosec
        _index_url("20220101"),
        text=_links(["enwiki_content-20220101-00000.json.bz2"]),
    )

    file_manager = FileManager("foo/bar", "a-project", BASE_URL, "en")

    assert file_manager.get_latest_dump_shards(None) == []


@pytest.mark.usefixtures("mock_gcs_client")
def test_get_latest_dump_shards_prefers_newest_complete_snapshot(requests_mock):
    """Pick the newest complete snapshot, skipping newer incomplete ones."""
    requests_mock.get(BASE_URL, text=_links(["20220101/", "20220108/"]))  # nosec
    # Newest snapshot is still being written.
    requests_mock.get(  # nosec
        _index_url("20220108"),
        text=_links(["enwiki_content-20220108-00000.json.bz2"]),
    )
    requests_mock.get(  # nosec
        _index_url("20220101"),
        text=_links(["enwiki_content-20220101-00000.json.bz2", "_SUCCESS"]),
    )

    file_manager = FileManager("foo/bar", "a-project", BASE_URL, "en")

    shard_urls = file_manager.get_latest_dump_shards(None)

    assert shard_urls == [f"{_index_url('20220101')}enwiki_content-20220101-00000.json.bz2"]


def test_get_latest_gcs(mock_gcs_client):
    """Test sorting logic for get_latest_gcs method"""
    blob1 = Blob("enwiki-20220101-cirrussearch-content.json.bz2", "foo")
    blob2 = Blob("enwiki-20210101-cirrussearch-content.json.bz2", "foo")

    mock_bucket = mock_gcs_client.bucket.return_value
    mock_bucket.list_blobs.return_value = [blob1, blob2]

    file_manager = FileManager("foo/bar", "a-project", "", "en")
    latest_gcs = file_manager.get_latest_gcs()

    assert latest_gcs == blob1


@patch("requests.head")
@patch("requests.get")
def test_stream_dump_to_gcs_success(
    mock_requests, mock_head, mock_gcs_client, mock_wiki_http_response
):
    """Test successful streaming of the sharded wiki dump into a single GCS blob"""
    shard_urls = [
        f"{_index_url('20220101')}enwiki_content-20220101-00000.json.bz2",
        f"{_index_url('20220101')}enwiki_content-20220101-00001.json.bz2",
    ]

    chunks = [b"chunk1", b"chunk2", b"chunk3"]

    mock_resp = mock_wiki_http_response(chunks)
    mock_requests.return_value.__enter__.return_value = mock_resp

    mock_head.return_value.headers = {"Content-Length": "18"}
    mock_head.return_value.raise_for_status.return_value = None

    mock_bucket = MagicMock()
    mock_gcs_client.bucket.return_value = mock_bucket

    mock_blob = MagicMock()
    mock_blob.name = "wiki-upload"
    mock_bucket.blob.return_value = mock_blob

    mock_blob_writer = MagicMock()
    mock_blob.open.return_value.__enter__.return_value = mock_blob_writer
    mock_blob.open.return_value.__exit__.return_value = None

    file_manager = FileManager(mock_bucket, "a-project", BASE_URL, "en")
    file_manager._stream_dump_to_gcs(shard_urls)

    # A single blob receives the concatenation of every shard.
    mock_blob.open.assert_called_once_with("wb")

    mock_blob_writer.write.assert_any_call(b"chunk1")
    mock_blob_writer.write.assert_any_call(b"chunk2")
    mock_blob_writer.write.assert_any_call(b"chunk3")

    assert mock_blob_writer.write.call_count == len(chunks) * len(shard_urls)


@patch("requests.head")
@patch("requests.get")
def test_stream_dump_to_gcs_blob_deletion(
    mock_requests, mock_head, mock_gcs_client, mock_wiki_http_response
):
    """Test deletion of partial upload on unsuccessful streaming of wiki dump to GCS"""
    shard_urls = [f"{_index_url('20220101')}enwiki_content-20220101-00000.json.bz2"]

    chunks = [b"chunk1", b"chunk2", b"chunk3"]
    mock_resp = mock_wiki_http_response(chunks)
    mock_requests.return_value.__enter__.return_value = mock_resp

    mock_head.return_value.headers = {"Content-Length": "18"}
    mock_head.return_value.raise_for_status.return_value = None

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

    file_manager = FileManager(mock_bucket, "a-project", BASE_URL, "en")

    with pytest.raises(WikipediaFilemanagerError, match="Failed to stream dump to GCS"):
        file_manager._stream_dump_to_gcs(shard_urls)

    mock_blob.exists.assert_called_once()
    mock_blob.delete.assert_called_once()
