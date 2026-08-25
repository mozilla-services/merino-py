# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the wikipedia indexer filemanager module."""

import bz2
from datetime import datetime
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest
from google.api_core.exceptions import GoogleAPIError
from requests import ConnectionError, HTTPError
from merino.jobs.wikipedia_indexer.filemanager import (
    DirectoryParser,
    FileManager,
    WikipediaFilemanagerError,
)
from merino.utils.wikipedia import WIKIMEDIA_REQUEST_HEADERS

BASE_URL = "http://mock-url/"


def _listing(hrefs: list[str]) -> str:
    """Render an Apache-style directory listing for the given hrefs."""
    links = "".join(f'<a href="{href}">{href}</a>' for href in hrefs)
    return f"<html><body><a href='../'>../</a>{links}</body></html>"


def _index_url(date: str, language: str = "fr") -> str:
    """Build the URL of a language's content index within a dated snapshot."""
    return f"{BASE_URL}{date}/index_name={language}wiki_content/"


def _shards(date: str, count: int, language: str = "fr") -> list[str]:
    """Build shard filenames as upstream publishes them."""
    return [f"{language}wiki_content-{date}-{i:05d}.json.bz2" for i in range(count)]


def _serve(pages: dict[str, list[str]]):
    """Build a requests.get side effect that serves directory listings by URL."""

    def _get(url, *args, **kwargs):
        if url not in pages:
            raise AssertionError(f"unexpected listing request: {url}")
        resp = MagicMock()
        resp.text = _listing(pages[url])
        resp.raise_for_status.return_value = None
        return resp

    return _get


def test_get_latest_gcs_returns_latest_blob():
    """Returns the most recent matching blob for a given language."""
    mock_client = MagicMock()
    mock_bucket = MagicMock()

    mock_blob_old = MagicMock()
    mock_blob_old.name = "frwiki-20240101-cirrussearch-content.json.bz2"

    mock_blob_new = MagicMock()
    mock_blob_new.name = "frwiki-20240401-cirrussearch-content.json.bz2"

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
    fr_blob.name = "frwiki-20240301-cirrussearch-content.json.bz2"

    en_blob = MagicMock()
    en_blob.name = "enwiki-20240301-cirrussearch-content.json.bz2"

    random_blob = MagicMock()
    random_blob.name = "unrelated-file.txt"

    mock_bucket.list_blobs.return_value = [fr_blob, en_blob, random_blob]
    mock_client.bucket.return_value = mock_bucket

    with patch("merino.jobs.wikipedia_indexer.filemanager.Client", return_value=mock_client):
        fm = FileManager("gcs-bucket", "gcs-project", "", language="fr")
        result = fm.get_latest_gcs()

    # the frwiki blob should match and be returned
    assert result == fr_blob


def test_get_latest_gcs_ignores_deprecated_gzip_dumps():
    """Ignores dumps left over from the deprecated gzip export layout."""
    mock_client = MagicMock()
    mock_bucket = MagicMock()

    legacy_blob = MagicMock()
    legacy_blob.name = "frwiki-20251229-cirrussearch-content.json.gz"

    mock_bucket.list_blobs.return_value = [legacy_blob]
    mock_client.bucket.return_value = mock_bucket

    with patch("merino.jobs.wikipedia_indexer.filemanager.Client", return_value=mock_client):
        fm = FileManager("gcs-bucket", "gcs-project", "", language="fr")

        with pytest.raises(RuntimeError, match="No matching dump files found"):
            fm.get_latest_gcs()


def test_get_latest_gcs_raises_runtime_error_if_no_matches():
    """Raises RuntimeError when no blobs match the language-specific pattern."""
    mock_client = MagicMock()
    mock_bucket = MagicMock()

    en_blob = MagicMock()
    en_blob.name = "enwiki-20240301-cirrussearch-content.json.bz2"

    unrelated_blob = MagicMock()
    unrelated_blob.name = "somefile.txt"

    mock_bucket.list_blobs.return_value = [en_blob, unrelated_blob]
    mock_client.bucket.return_value = mock_bucket

    with patch("merino.jobs.wikipedia_indexer.filemanager.Client", return_value=mock_client):
        fm = FileManager("gcs-bucket", "gcs-project", "", language="fr")

        with pytest.raises(RuntimeError, match="No matching dump files found"):
            fm.get_latest_gcs()


def test_directory_parser_decodes_percent_encoded_hrefs():
    """Decodes percent-encoded hrefs, as used for the 'index_name=' subdirectories."""
    parser = DirectoryParser()
    parser.feed('<a href="index_name%3Dfrwiki_content/" class="dir">frwiki_content</a>')

    assert parser.file_paths == ["index_name=frwiki_content/"]


def test_directory_parser_ignores_valueless_attributes():
    """Ignores anchors whose href attribute carries no value."""
    parser = DirectoryParser()
    parser.feed('<a href>empty</a><a href="20240401/">20240401/</a>')

    assert parser.file_paths == ["20240401/"]


def test_directory_parser_collects_every_href():
    """Collects all anchor hrefs, including navigation, and ignores other tags."""
    parser = DirectoryParser()
    parser.feed(
        "<html><body><a href='../'>../</a><img src='icon.png'/>"
        "<a href='20240401/'>20240401/</a><a href='_SUCCESS'>_SUCCESS</a></body></html>"
    )

    assert parser.file_paths == ["../", "20240401/", "_SUCCESS"]


@patch("merino.jobs.wikipedia_indexer.filemanager.requests.get")
def test_get_latest_dump_shards_returns_ordered_shards(mock_get):
    """Returns every shard of the newest complete snapshot, in shard order."""
    mock_get.side_effect = _serve(
        {
            BASE_URL: ["20240301/", "20240401/"],
            _index_url("20240401"): [*_shards("20240401", 3), "_SUCCESS"],
        }
    )

    mock_blob = MagicMock()
    mock_blob.name = "frwiki-20240301-cirrussearch-content.json.bz2"  # older GCS file

    mock_client = MagicMock()
    with patch("merino.jobs.wikipedia_indexer.filemanager.Client", return_value=mock_client):
        fm = FileManager("gcs-bucket", "gcs-project", BASE_URL, "fr")
        result = fm.get_latest_dump_shards(mock_blob)

    index_url = _index_url("20240401")
    assert result == [
        f"{index_url}frwiki_content-20240401-00000.json.bz2",
        f"{index_url}frwiki_content-20240401-00001.json.bz2",
        f"{index_url}frwiki_content-20240401-00002.json.bz2",
    ]


@patch("merino.jobs.wikipedia_indexer.filemanager.requests.get")
def test_get_latest_dump_shards_orders_numerically_not_lexically(mock_get):
    """Orders shards by shard number so a padding width change cannot reorder them."""
    mock_get.side_effect = _serve(
        {
            BASE_URL: ["20240401/"],
            _index_url("20240401"): [
                "frwiki_content-20240401-10.json.bz2",
                "frwiki_content-20240401-9.json.bz2",
                "frwiki_content-20240401-00002.json.bz2",
                "_SUCCESS",
            ],
        }
    )

    mock_client = MagicMock()
    with patch("merino.jobs.wikipedia_indexer.filemanager.Client", return_value=mock_client):
        fm = FileManager("gcs-bucket", "gcs-project", BASE_URL, "fr")
        result = fm.get_latest_dump_shards(None)

    assert [url.rsplit("-", 1)[-1] for url in result] == [
        "00002.json.bz2",
        "9.json.bz2",
        "10.json.bz2",
    ]


@patch("merino.jobs.wikipedia_indexer.filemanager.requests.get")
def test_get_latest_dump_shards_when_gcs_is_none(mock_get):
    """Returns the newest snapshot's shards on first run when no GCS file exists."""
    mock_get.side_effect = _serve(
        {
            BASE_URL: ["20250512/"],
            _index_url("20250512", "de"): [*_shards("20250512", 1, "de"), "_SUCCESS"],
        }
    )

    mock_client = MagicMock()
    with patch("merino.jobs.wikipedia_indexer.filemanager.Client", return_value=mock_client):
        fm = FileManager("gcs-bucket", "gcs-project", BASE_URL, "de")
        result = fm.get_latest_dump_shards(latest_gcs=None)

    assert result == [f"{_index_url('20250512', 'de')}dewiki_content-20250512-00000.json.bz2"]


@patch("merino.jobs.wikipedia_indexer.filemanager.requests.get")
def test_get_latest_dump_shards_returns_empty_if_not_newer(mock_get):
    """Returns no shards when the latest snapshot is not newer than the GCS dump."""
    mock_get.side_effect = _serve({BASE_URL: ["20240301/"]})

    mock_blob = MagicMock()
    mock_blob.name = "frwiki-20240301-cirrussearch-content.json.bz2"  # same date

    mock_client = MagicMock()
    with patch("merino.jobs.wikipedia_indexer.filemanager.Client", return_value=mock_client):
        fm = FileManager("gcs-bucket", "gcs-project", BASE_URL, "fr")
        result = fm.get_latest_dump_shards(mock_blob)

    assert result == []


@patch("merino.jobs.wikipedia_indexer.filemanager.requests.get")
def test_get_latest_dump_shards_skips_snapshot_without_success_marker(mock_get):
    """Falls back to the previous snapshot when the newest is not fully published."""
    mock_get.side_effect = _serve(
        {
            BASE_URL: ["20240301/", "20240401/"],
            # Newest snapshot is still being written: shards present, no marker.
            _index_url("20240401"): _shards("20240401", 2),
            _index_url("20240301"): [*_shards("20240301", 1), "_SUCCESS"],
        }
    )

    mock_client = MagicMock()
    with patch("merino.jobs.wikipedia_indexer.filemanager.Client", return_value=mock_client):
        fm = FileManager("gcs-bucket", "gcs-project", BASE_URL, "fr")
        result = fm.get_latest_dump_shards(None)

    assert result == [f"{_index_url('20240301')}frwiki_content-20240301-00000.json.bz2"]


@patch("merino.jobs.wikipedia_indexer.filemanager.requests.get")
def test_get_latest_dump_shards_returns_empty_when_no_snapshot_is_complete(mock_get):
    """Returns no shards when every available snapshot is still incomplete."""
    mock_get.side_effect = _serve(
        {
            BASE_URL: ["20240301/", "20240401/"],
            _index_url("20240401"): _shards("20240401", 2),  # no marker
            _index_url("20240301"): [],  # export missing entirely
        }
    )

    mock_client = MagicMock()
    with patch("merino.jobs.wikipedia_indexer.filemanager.Client", return_value=mock_client):
        fm = FileManager("gcs-bucket", "gcs-project", BASE_URL, "fr")
        result = fm.get_latest_dump_shards(None)

    assert result == []


@patch("merino.jobs.wikipedia_indexer.filemanager.requests.get")
def test_get_latest_dump_shards_does_not_walk_past_gcs_date(mock_get):
    """Stops at the GCS dump's date rather than re-copying an older snapshot."""
    # _serve raises if the 20240301 listing is requested, which it must not be.
    mock_get.side_effect = _serve(
        {
            BASE_URL: ["20240301/", "20240401/"],
            _index_url("20240401"): _shards("20240401", 2),  # incomplete, no marker
        }
    )

    mock_blob = MagicMock()
    mock_blob.name = "frwiki-20240301-cirrussearch-content.json.bz2"

    mock_client = MagicMock()
    with patch("merino.jobs.wikipedia_indexer.filemanager.Client", return_value=mock_client):
        fm = FileManager("gcs-bucket", "gcs-project", BASE_URL, "fr")
        result = fm.get_latest_dump_shards(mock_blob)

    assert result == []


@patch("merino.jobs.wikipedia_indexer.filemanager.requests.get")
def test_get_latest_dump_shards_skips_snapshot_that_fails_to_list(mock_get):
    """Skips to an older snapshot when listing the newest one errors."""
    serve = _serve(
        {
            BASE_URL: ["20240301/", "20240401/"],
            _index_url("20240301"): [*_shards("20240301", 1), "_SUCCESS"],
        }
    )

    def _get(url, *args, **kwargs):
        if url == _index_url("20240401"):
            raise ConnectionError("Simulated listing failure")
        return serve(url)

    mock_get.side_effect = _get

    mock_client = MagicMock()
    with patch("merino.jobs.wikipedia_indexer.filemanager.Client", return_value=mock_client):
        fm = FileManager("gcs-bucket", "gcs-project", BASE_URL, "fr")
        result = fm.get_latest_dump_shards(None)

    assert result == [f"{_index_url('20240301')}frwiki_content-20240301-00000.json.bz2"]


@patch("merino.jobs.wikipedia_indexer.filemanager.requests.get")
def test_get_latest_dump_shards_ignores_non_snapshot_entries(mock_get):
    """Ignores directory entries that are not dated snapshots."""
    mock_get.side_effect = _serve(
        {
            # "99999999/" has the right shape but is not a real date.
            BASE_URL: ["DEPRECATED.txt", "current/", "99999999/", "20240401/"],
            _index_url("20240401"): [*_shards("20240401", 1), "_SUCCESS"],
        }
    )

    mock_client = MagicMock()
    with patch("merino.jobs.wikipedia_indexer.filemanager.Client", return_value=mock_client):
        fm = FileManager("gcs-bucket", "gcs-project", BASE_URL, "fr")
        result = fm.get_latest_dump_shards(None)

    assert result == [f"{_index_url('20240401')}frwiki_content-20240401-00000.json.bz2"]


@patch("merino.jobs.wikipedia_indexer.filemanager.requests.head")
@patch("merino.jobs.wikipedia_indexer.filemanager.requests.get")
def test_stream_dump_to_gcs_concatenates_shards(mock_get, mock_head):
    """Copies each shard's raw bytes into a single blob named for the snapshot date."""
    mock_chunk = b"x" * 1024

    def _shard_response(url, *args, **kwargs):
        resp = MagicMock()
        resp.__enter__.return_value = resp
        resp.iter_content.return_value = [mock_chunk]
        resp.raise_for_status.return_value = None
        return resp

    mock_get.side_effect = _shard_response

    head_resp = MagicMock()
    head_resp.headers = {"Content-Length": str(len(mock_chunk))}
    head_resp.raise_for_status.return_value = None
    mock_head.return_value = head_resp

    mock_writer = MagicMock()
    mock_writer.write.side_effect = lambda chunk: len(chunk)

    mock_blob = MagicMock()
    mock_blob.open.return_value.__enter__.return_value = mock_writer

    mock_bucket = MagicMock()
    mock_bucket.blob.return_value = mock_blob

    mock_client = MagicMock()
    mock_client.bucket.return_value = mock_bucket

    index_url = _index_url("20240501")
    shard_urls = [f"{index_url}{name}" for name in _shards("20240501", 2)]

    with patch("merino.jobs.wikipedia_indexer.filemanager.Client", return_value=mock_client):
        fm = FileManager("gcs-bucket/exports", "gcs-project", BASE_URL, "fr")
        fm._stream_dump_to_gcs(shard_urls)

    # One write per shard, into a single blob opened once for the whole concatenation.
    assert mock_writer.write.call_count == 2
    mock_blob.open.assert_called_once()
    assert mock_get.call_count == 2
    # Wikimedia 403s requests that do not identify themselves.
    mock_get.assert_any_call(shard_urls[0], stream=True, headers=WIKIMEDIA_REQUEST_HEADERS)
    # The reassembled dump keeps the historical single-file naming convention.
    assert (
        mock_bucket.blob.call_args.args[0]
        == "exports/frwiki-20240501-cirrussearch-content.json.bz2"
    )


@patch("merino.jobs.wikipedia_indexer.filemanager.requests.head")
@patch("merino.jobs.wikipedia_indexer.filemanager.requests.get")
def test_stream_dump_to_gcs_copies_when_size_unknown(mock_get, mock_head):
    """Still copies the shards when shard sizes cannot be read for progress reporting."""
    mock_head.side_effect = ConnectionError("Simulated HEAD failure")

    resp = MagicMock()
    resp.__enter__.return_value = resp
    resp.iter_content.return_value = [b"y" * 512]
    resp.raise_for_status.return_value = None
    mock_get.return_value = resp

    mock_writer = MagicMock()
    mock_writer.write.side_effect = lambda chunk: len(chunk)

    mock_blob = MagicMock()
    mock_blob.open.return_value.__enter__.return_value = mock_writer

    mock_bucket = MagicMock()
    mock_bucket.blob.return_value = mock_blob

    mock_client = MagicMock()
    mock_client.bucket.return_value = mock_bucket

    with patch("merino.jobs.wikipedia_indexer.filemanager.Client", return_value=mock_client):
        fm = FileManager("gcs-bucket", "gcs-project", BASE_URL, "fr")
        fm._stream_dump_to_gcs([f"{_index_url('20240501')}frwiki_content-20240501-00000.json.bz2"])

    mock_writer.write.assert_called_once()


@patch("merino.jobs.wikipedia_indexer.filemanager.requests.head")
@patch("merino.jobs.wikipedia_indexer.filemanager.requests.get")
def test_stream_dump_to_gcs_handles_stream_failure_and_deletes_blob(mock_get, mock_head):
    """Handles stream failure by deleting the partial GCS blob and raising an error."""
    head_resp = MagicMock()
    head_resp.headers = {"Content-Length": "1024"}
    head_resp.raise_for_status.return_value = None
    mock_head.return_value = head_resp

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
        fm = FileManager("gcs-bucket", "gcs-project", BASE_URL, "fr")

        with pytest.raises(WikipediaFilemanagerError, match="Failed to stream dump to GCS"):
            fm._stream_dump_to_gcs(
                [f"{_index_url('20240501')}frwiki_content-20240501-00000.json.bz2"]
            )

    mock_blob.exists.assert_called_once()
    mock_blob.delete.assert_called_once()


@patch("merino.jobs.wikipedia_indexer.filemanager.requests.head")
@patch("merino.jobs.wikipedia_indexer.filemanager.requests.get")
def test_stream_dump_to_gcs_skips_delete_when_no_partial_blob(mock_get, mock_head):
    """Does not attempt a delete when the failed copy left no blob behind."""
    mock_head.side_effect = ConnectionError("Simulated HEAD failure")

    mock_response = MagicMock()
    mock_response.__enter__.return_value = mock_response
    mock_response.raise_for_status.side_effect = HTTPError("Simulated HTTP error")
    mock_get.return_value = mock_response

    mock_blob = MagicMock()
    mock_blob.exists.return_value = False

    mock_bucket = MagicMock()
    mock_bucket.blob.return_value = mock_blob

    mock_client = MagicMock()
    mock_client.bucket.return_value = mock_bucket

    with patch("merino.jobs.wikipedia_indexer.filemanager.Client", return_value=mock_client):
        fm = FileManager("gcs-bucket", "gcs-project", BASE_URL, "fr")

        with pytest.raises(WikipediaFilemanagerError, match="Failed to stream dump to GCS"):
            fm._stream_dump_to_gcs(
                [f"{_index_url('20240501')}frwiki_content-20240501-00000.json.bz2"]
            )

    mock_blob.delete.assert_not_called()


@patch("merino.jobs.wikipedia_indexer.filemanager.requests.head")
@patch("merino.jobs.wikipedia_indexer.filemanager.requests.get")
def test_stream_dump_to_gcs_still_raises_when_cleanup_fails(mock_get, mock_head):
    """Reports the streaming failure even when deleting the partial upload also fails."""
    mock_head.side_effect = ConnectionError("Simulated HEAD failure")

    mock_response = MagicMock()
    mock_response.__enter__.return_value = mock_response
    mock_response.raise_for_status.side_effect = HTTPError("Simulated HTTP error")
    mock_get.return_value = mock_response

    mock_blob = MagicMock()
    mock_blob.exists.return_value = True
    mock_blob.delete.side_effect = GoogleAPIError("Simulated delete failure")

    mock_bucket = MagicMock()
    mock_bucket.blob.return_value = mock_blob

    mock_client = MagicMock()
    mock_client.bucket.return_value = mock_bucket

    with patch("merino.jobs.wikipedia_indexer.filemanager.Client", return_value=mock_client):
        fm = FileManager("gcs-bucket", "gcs-project", BASE_URL, "fr")

        with pytest.raises(WikipediaFilemanagerError, match="Failed to stream dump to GCS"):
            fm._stream_dump_to_gcs(
                [f"{_index_url('20240501')}frwiki_content-20240501-00000.json.bz2"]
            )

    mock_blob.delete.assert_called_once()


def test_stream_dump_to_gcs_rejects_unrecognized_shard_name():
    """Raises rather than guessing when a shard URL does not match the expected form."""
    mock_client = MagicMock()
    with patch("merino.jobs.wikipedia_indexer.filemanager.Client", return_value=mock_client):
        fm = FileManager("gcs-bucket", "gcs-project", BASE_URL, "fr")

        with pytest.raises(WikipediaFilemanagerError, match="Unrecognized shard name"):
            fm._stream_dump_to_gcs(["http://mock-url/not-a-shard.json.bz2"])


@patch.object(FileManager, "_stream_dump_to_gcs")
@patch.object(FileManager, "get_latest_dump_shards")
@patch.object(FileManager, "get_latest_gcs")
def test_stream_latest_dump_triggers_stream(
    mock_get_latest_gcs, mock_get_latest_shards, mock_stream
):
    """Triggers dump streaming when a newer remote dump is available."""
    mock_client = MagicMock()
    mock_blob = MagicMock()
    mock_get_latest_gcs.return_value = mock_blob
    shard_urls = [f"{_index_url('20240501')}frwiki_content-20240501-00000.json.bz2"]
    mock_get_latest_shards.return_value = shard_urls

    with patch("merino.jobs.wikipedia_indexer.filemanager.Client", return_value=mock_client):
        fm = FileManager("gcs-bucket", "gcs-project", BASE_URL, "fr")
        returned_blob = fm.stream_latest_dump_to_gcs()

    mock_stream.assert_called_once_with(shard_urls)
    assert returned_blob == mock_blob


@patch.object(FileManager, "_stream_dump_to_gcs")
@patch.object(FileManager, "get_latest_dump_shards")
@patch.object(FileManager, "get_latest_gcs")
def test_stream_latest_dump_uses_caller_supplied_blob(
    mock_get_latest_gcs, mock_get_latest_shards, mock_stream
):
    """Does not re-list GCS when the caller already knows the latest blob."""
    mock_client = MagicMock()
    caller_blob = MagicMock()
    caller_blob.name = "frwiki-20240301-cirrussearch-content.json.bz2"
    mock_get_latest_shards.return_value = []

    with patch("merino.jobs.wikipedia_indexer.filemanager.Client", return_value=mock_client):
        fm = FileManager("gcs-bucket", "gcs-project", BASE_URL, "fr")
        returned_blob = fm.stream_latest_dump_to_gcs(latest_gcs=caller_blob)

    mock_get_latest_gcs.assert_not_called()
    mock_get_latest_shards.assert_called_once_with(caller_blob)
    assert returned_blob == caller_blob


@patch.object(FileManager, "_stream_dump_to_gcs")
@patch.object(FileManager, "get_latest_dump_shards")
@patch.object(FileManager, "get_latest_gcs")
def test_stream_latest_dump_skips_if_up_to_date(
    mock_get_latest_gcs, mock_get_latest_shards, mock_stream
):
    """Skips dump streaming when no newer dump is available."""
    mock_client = MagicMock()
    mock_blob = MagicMock()
    mock_get_latest_gcs.return_value = mock_blob
    mock_get_latest_shards.return_value = []  # No newer dump

    with patch("merino.jobs.wikipedia_indexer.filemanager.Client", return_value=mock_client):
        fm = FileManager("gcs-bucket", "gcs-project", BASE_URL, "fr")
        returned_blob = fm.stream_latest_dump_to_gcs()

    mock_stream.assert_not_called()
    assert returned_blob == mock_blob


@patch.object(FileManager, "_stream_dump_to_gcs")
@patch.object(FileManager, "get_latest_dump_shards")
@patch.object(FileManager, "get_latest_gcs")
def test_stream_latest_dump_when_gcs_empty(
    mock_get_latest_gcs, mock_get_latest_shards, mock_stream
):
    """Triggers streaming when no prior GCS dump exists (first-time run)."""
    mock_client = MagicMock()

    mock_blob = MagicMock()
    mock_blob.name = "BlobMock"

    # First call raises RuntimeError (no file)
    mock_get_latest_gcs.side_effect = [
        RuntimeError("No matching dump files found"),
        mock_blob,
    ]
    shard_urls = [f"{_index_url('20250512', 'de')}dewiki_content-20250512-00000.json.bz2"]
    mock_get_latest_shards.return_value = shard_urls

    with patch("merino.jobs.wikipedia_indexer.filemanager.Client", return_value=mock_client):
        fm = FileManager("gcs-bucket", "gcs-project", BASE_URL, "de")
        returned_blob = fm.stream_latest_dump_to_gcs()

    mock_stream.assert_called_once_with(shard_urls)
    assert returned_blob.name == "BlobMock"


def test_stream_from_gcs_reads_concatenated_bz2_shards():
    """Reads a blob of concatenated bzip2 shards as one continuous line stream."""
    first = bz2.compress(b'{"index": {"_id": 1}}\n{"title": "One"}\n')
    second = bz2.compress(b'{"index": {"_id": 2}}\n{"title": "Two"}\n')

    mock_blob = MagicMock()
    mock_blob.name = "frwiki-20240501-cirrussearch-content.json.bz2"
    mock_blob.open.return_value.__enter__.return_value = BytesIO(first + second)

    mock_client = MagicMock()
    with patch("merino.jobs.wikipedia_indexer.filemanager.Client", return_value=mock_client):
        fm = FileManager("gcs-bucket", "gcs-project", BASE_URL, "fr")
        lines = list(fm.stream_from_gcs(mock_blob))

    assert lines == [
        b'{"index": {"_id": 1}}\n',
        b'{"title": "One"}\n',
        b'{"index": {"_id": 2}}\n',
        b'{"title": "Two"}\n',
    ]


def test_parse_date_returns_correct_datetime():
    """Parses and returns the correct datetime from a valid filename."""
    mock_client = MagicMock()
    with patch("merino.jobs.wikipedia_indexer.filemanager.Client", return_value=mock_client):
        fm = FileManager("gcs-bucket", "gcs-project", BASE_URL, "fr")

        filename = "frwiki-20240501-cirrussearch-content.json.bz2"
        result = fm._parse_date(filename)

        assert isinstance(result, datetime)
        assert result == datetime(2024, 5, 1)


def test_parse_date_returns_default_on_invalid_filename():
    """Returns the default fallback datetime when the filename is invalid."""
    mock_client = MagicMock()
    with patch("merino.jobs.wikipedia_indexer.filemanager.Client", return_value=mock_client):
        fm = FileManager("gcs-bucket", "gcs-project", BASE_URL, "fr")

        filename = "invalid-file-name.txt"
        result = fm._parse_date(filename)

        assert result == datetime(1, 1, 1)


def test_parse_date_returns_default_on_impossible_date():
    """Returns the default fallback datetime when a well-formed name holds a bad date."""
    mock_client = MagicMock()
    with patch("merino.jobs.wikipedia_indexer.filemanager.Client", return_value=mock_client):
        fm = FileManager("gcs-bucket", "gcs-project", BASE_URL, "fr")

        # January 32nd: matches the pattern but is not a date.
        result = fm._parse_date("frwiki-20240132-cirrussearch-content.json.bz2")

        assert result == datetime(1, 1, 1)


def test_filemanager_rejects_invalid_language():
    """Raises ValueError if FileManager is initialized with an unsupported language."""
    with pytest.raises(ValueError, match="Unsupported language 'es'"):
        FileManager("gcs-bucket", "gcs-project", "http://mock-url", language="es")
