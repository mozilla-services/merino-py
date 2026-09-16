# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the wikipedia indexer filemanager module."""

import bz2
from datetime import datetime as dt
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest
from requests import ConnectionError

from merino.jobs.wikipedia_indexer.filemanager import (
    SUCCESS_MARKER,
    DirectoryParser,
    FileManager,
    Snapshot,
    WikipediaFilemanagerError,
)

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
    """Build a session.get side effect that serves directory listings by URL."""

    def _get(url, *args, **kwargs):
        if url not in pages:
            raise AssertionError(f"unexpected listing request: {url}")
        resp = MagicMock()
        resp.text = _listing(pages[url])
        resp.raise_for_status.return_value = None
        return resp

    return _get


def _gcs_blob(name: str, size: int = 0) -> MagicMock:
    """Build a GCS blob mock with a name and size."""
    blob = MagicMock()
    blob.name = name
    blob.size = size
    return blob


@pytest.fixture(name="session")
def fixture_session(mocker):
    """Replace the pooled Wikimedia session so requests can be scripted."""
    session = MagicMock()
    mocker.patch.object(FileManager, "_build_session", return_value=session)
    return session


@pytest.fixture(name="gcs_client")
def fixture_gcs_client():
    """Return a mock GCS client whose bucket returns a single configurable mock."""
    client = MagicMock()
    bucket = MagicMock()
    client.bucket.return_value = bucket
    return client


def _file_manager(
    gcs_client, language: str = "fr", gcs_bucket: str = "gcs-bucket", base_url: str = BASE_URL
) -> FileManager:
    """Build a FileManager with its GCS client replaced."""
    with patch("merino.jobs.wikipedia_indexer.filemanager.Client", return_value=gcs_client):
        return FileManager(gcs_bucket, "gcs-project", base_url, language)


def test_directory_parser_decodes_percent_encoded_hrefs():
    """Decode percent-encoded hrefs, as used for the 'index_name=' subdirectories."""
    parser = DirectoryParser()
    parser.feed('<a href="index_name%3Dfrwiki_content/" class="dir">frwiki_content</a>')

    assert parser.file_paths == ["index_name=frwiki_content/"]


def test_directory_parser_ignores_valueless_attributes():
    """Ignore anchors whose href attribute carries no value."""
    parser = DirectoryParser()
    parser.feed('<a href>empty</a><a href="20240401/">20240401/</a>')

    assert parser.file_paths == ["20240401/"]


def test_directory_parser_collects_every_href():
    """Collect all anchor hrefs, including navigation, and ignore other tags."""
    parser = DirectoryParser()
    parser.feed(
        "<html><body><a href='../'>../</a><img src='icon.png'/>"
        "<a href='20240401/'>20240401/</a><a href='_SUCCESS'>_SUCCESS</a></body></html>"
    )

    assert parser.file_paths == ["../", "20240401/", "_SUCCESS"]


@pytest.mark.parametrize(
    ["gcs_bucket", "expected_bucket", "expected_prefix"],
    [
        ("bucket-only", "bucket-only", ""),
        ("bucket/prefix", "bucket", "prefix"),
        ("bucket/nested/prefix", "bucket", "nested/prefix"),
    ],
    ids=["no_prefix", "single_prefix", "nested_prefix"],
)
def test_parse_gcs_bucket(gcs_client, gcs_bucket, expected_bucket, expected_prefix):
    """Split the configured GCS path into a bucket and an object prefix."""
    fm = _file_manager(gcs_client, gcs_bucket=gcs_bucket)

    assert fm.gcs_bucket == expected_bucket
    assert fm.object_prefix == expected_prefix


@pytest.mark.parametrize(
    ["gcs_bucket", "expected_prefix"],
    [
        ("bucket-only", "frwiki-20240401-cirrussearch-content"),
        ("bucket/exports", "exports/frwiki-20240401-cirrussearch-content"),
    ],
    ids=["no_prefix", "with_prefix"],
)
def test_snapshot_for_builds_name_and_prefix(gcs_client, gcs_bucket, expected_prefix):
    """Build the snapshot prefix from the language and date."""
    fm = _file_manager(gcs_client, gcs_bucket=gcs_bucket)

    snapshot = fm.snapshot_for(dt(2024, 4, 1))

    # The name keeps the shape the old single-object layout used, so it still works
    # as the basis for the Elasticsearch index name.
    assert snapshot.name == "frwiki-20240401-cirrussearch-content"
    assert snapshot.prefix == expected_prefix
    assert snapshot.date == dt(2024, 4, 1)


def test_filemanager_rejects_invalid_language(gcs_client):
    """Raise ValueError for a language the service does not support."""
    with pytest.raises(ValueError, match="Unsupported language 'es'"):
        _file_manager(gcs_client, language="es")


def test_get_latest_gcs_returns_newest_complete_snapshot(gcs_client):
    """Return the most recent snapshot that has a success marker."""
    gcs_client.bucket.return_value.list_blobs.return_value = [
        _gcs_blob(f"frwiki-20240101-cirrussearch-content/{SUCCESS_MARKER}"),
        _gcs_blob("frwiki-20240401-cirrussearch-content/frwiki_content-20240401-00000.json.bz2"),
        _gcs_blob(f"frwiki-20240401-cirrussearch-content/{SUCCESS_MARKER}"),
    ]
    fm = _file_manager(gcs_client)

    latest = fm.get_latest_gcs()

    assert latest is not None
    assert latest.date == dt(2024, 4, 1)


def test_get_latest_gcs_ignores_snapshot_without_success_marker(gcs_client):
    """Ignore a newer snapshot whose copy has not finished.

    Shards land one object at a time, so a prefix full of shards but missing the
    marker is a copy still in flight or abandoned by a failed run.
    """
    gcs_client.bucket.return_value.list_blobs.return_value = [
        _gcs_blob(f"frwiki-20240101-cirrussearch-content/{SUCCESS_MARKER}"),
        # Newer, but only partially copied.
        _gcs_blob("frwiki-20240401-cirrussearch-content/frwiki_content-20240401-00000.json.bz2"),
        _gcs_blob("frwiki-20240401-cirrussearch-content/frwiki_content-20240401-00001.json.bz2"),
    ]
    fm = _file_manager(gcs_client)

    latest = fm.get_latest_gcs()

    assert latest is not None
    assert latest.date == dt(2024, 1, 1)


def test_get_latest_gcs_filters_by_language(gcs_client):
    """Ignore complete snapshots belonging to another language."""
    gcs_client.bucket.return_value.list_blobs.return_value = [
        _gcs_blob(f"enwiki-20240401-cirrussearch-content/{SUCCESS_MARKER}"),
        _gcs_blob(f"frwiki-20240301-cirrussearch-content/{SUCCESS_MARKER}"),
    ]
    fm = _file_manager(gcs_client)

    latest = fm.get_latest_gcs()

    assert latest is not None
    assert latest.name == "frwiki-20240301-cirrussearch-content"


@pytest.mark.parametrize(
    "blob_names",
    [
        [],
        ["somefile.txt"],
        # The deprecated single-object gzip and bz2 layouts are no longer recognized.
        ["frwiki-20240401-cirrussearch-content.json.gz"],
        ["frwiki-20240401-cirrussearch-content.json.bz2"],
        # Right shape, impossible date.
        [f"frwiki-20240132-cirrussearch-content/{SUCCESS_MARKER}"],
    ],
    ids=["empty", "unrelated", "legacy_gzip", "legacy_bz2", "impossible_date"],
)
def test_get_latest_gcs_returns_none_when_nothing_is_usable(gcs_client, blob_names):
    """Return None when no complete snapshot exists in the new layout."""
    gcs_client.bucket.return_value.list_blobs.return_value = [
        _gcs_blob(name) for name in blob_names
    ]
    fm = _file_manager(gcs_client)

    assert fm.get_latest_gcs() is None


def test_get_latest_dump_shards_returns_ordered_shards(gcs_client, session):
    """Return every shard of the newest complete snapshot, in shard order."""
    session.get.side_effect = _serve(
        {
            BASE_URL: ["20240301/", "20240401/"],
            _index_url("20240401"): [*_shards("20240401", 3), SUCCESS_MARKER],
        }
    )
    fm = _file_manager(gcs_client)

    result = fm.get_latest_dump_shards(fm.snapshot_for(dt(2024, 3, 1)))

    index_url = _index_url("20240401")
    assert result == [
        f"{index_url}frwiki_content-20240401-00000.json.bz2",
        f"{index_url}frwiki_content-20240401-00001.json.bz2",
        f"{index_url}frwiki_content-20240401-00002.json.bz2",
    ]


def test_get_latest_dump_shards_orders_numerically_not_lexically(gcs_client, session):
    """Order shards by shard number so a padding width change cannot reorder them."""
    session.get.side_effect = _serve(
        {
            BASE_URL: ["20240401/"],
            _index_url("20240401"): [
                "frwiki_content-20240401-10.json.bz2",
                "frwiki_content-20240401-9.json.bz2",
                "frwiki_content-20240401-00002.json.bz2",
                SUCCESS_MARKER,
            ],
        }
    )
    fm = _file_manager(gcs_client)

    result = fm.get_latest_dump_shards(None)

    assert [url.rsplit("-", 1)[-1] for url in result] == [
        "00002.json.bz2",
        "9.json.bz2",
        "10.json.bz2",
    ]


def test_get_latest_dump_shards_when_gcs_is_none(gcs_client, session):
    """Return the newest snapshot's shards on first run when GCS is empty."""
    session.get.side_effect = _serve(
        {
            BASE_URL: ["20250512/"],
            _index_url("20250512", "de"): [*_shards("20250512", 1, "de"), SUCCESS_MARKER],
        }
    )
    fm = _file_manager(gcs_client, language="de")

    result = fm.get_latest_dump_shards(latest_gcs=None)

    assert result == [f"{_index_url('20250512', 'de')}dewiki_content-20250512-00000.json.bz2"]


def test_get_latest_dump_shards_returns_empty_if_not_newer(gcs_client, session):
    """Return no shards when the latest snapshot is not newer than the GCS copy."""
    session.get.side_effect = _serve({BASE_URL: ["20240301/"]})
    fm = _file_manager(gcs_client)

    result = fm.get_latest_dump_shards(fm.snapshot_for(dt(2024, 3, 1)))

    assert result == []


def test_get_latest_dump_shards_skips_snapshot_without_success_marker(gcs_client, session):
    """Fall back to the previous snapshot when the newest is not fully published."""
    session.get.side_effect = _serve(
        {
            BASE_URL: ["20240301/", "20240401/"],
            # Newest snapshot is still being written: shards present, no marker.
            _index_url("20240401"): _shards("20240401", 2),
            _index_url("20240301"): [*_shards("20240301", 1), SUCCESS_MARKER],
        }
    )
    fm = _file_manager(gcs_client)

    result = fm.get_latest_dump_shards(None)

    assert result == [f"{_index_url('20240301')}frwiki_content-20240301-00000.json.bz2"]


def test_get_latest_dump_shards_returns_empty_when_no_snapshot_is_complete(gcs_client, session):
    """Return no shards when every available snapshot is still incomplete."""
    session.get.side_effect = _serve(
        {
            BASE_URL: ["20240301/", "20240401/"],
            _index_url("20240401"): _shards("20240401", 2),  # no marker
            _index_url("20240301"): [],  # export missing entirely
        }
    )
    fm = _file_manager(gcs_client)

    assert fm.get_latest_dump_shards(None) == []


def test_get_latest_dump_shards_does_not_walk_past_gcs_date(gcs_client, session):
    """Stop at the GCS copy's date rather than re-copying an older snapshot."""
    # _serve raises if the 20240301 listing is requested, which it must not be.
    session.get.side_effect = _serve(
        {
            BASE_URL: ["20240301/", "20240401/"],
            _index_url("20240401"): _shards("20240401", 2),  # incomplete, no marker
        }
    )
    fm = _file_manager(gcs_client)

    assert fm.get_latest_dump_shards(fm.snapshot_for(dt(2024, 3, 1))) == []


def test_get_latest_dump_shards_skips_snapshot_that_fails_to_list(gcs_client, session):
    """Skip to an older snapshot when listing the newest one errors."""
    serve = _serve(
        {
            BASE_URL: ["20240301/", "20240401/"],
            _index_url("20240301"): [*_shards("20240301", 1), SUCCESS_MARKER],
        }
    )

    def _get(url, *args, **kwargs):
        if url == _index_url("20240401"):
            raise ConnectionError("Simulated listing failure")
        return serve(url)

    session.get.side_effect = _get
    fm = _file_manager(gcs_client)

    result = fm.get_latest_dump_shards(None)

    assert result == [f"{_index_url('20240301')}frwiki_content-20240301-00000.json.bz2"]


def test_get_latest_dump_shards_ignores_non_snapshot_entries(gcs_client, session):
    """Ignore directory entries that are not dated snapshots."""
    session.get.side_effect = _serve(
        {
            # "99999999/" has the right shape but is not a real date.
            BASE_URL: ["DEPRECATED.txt", "current/", "99999999/", "20240401/"],
            _index_url("20240401"): [*_shards("20240401", 1), SUCCESS_MARKER],
        }
    )
    fm = _file_manager(gcs_client)

    result = fm.get_latest_dump_shards(None)

    assert result == [f"{_index_url('20240401')}frwiki_content-20240401-00000.json.bz2"]


def test_list_gcs_shards_orders_numerically_and_ignores_other_objects(gcs_client):
    """Return only shard objects, ordered by shard number."""
    prefix = "frwiki-20240401-cirrussearch-content"
    gcs_client.bucket.return_value.list_blobs.return_value = [
        _gcs_blob(f"{prefix}/frwiki_content-20240401-00010.json.bz2"),
        _gcs_blob(f"{prefix}/{SUCCESS_MARKER}"),
        _gcs_blob(f"{prefix}/frwiki_content-20240401-00002.json.bz2"),
        _gcs_blob(f"{prefix}/unrelated.txt"),
    ]
    fm = _file_manager(gcs_client)

    shards = fm.list_gcs_shards(fm.snapshot_for(dt(2024, 4, 1)))

    assert [str(blob.name).rsplit("-", 1)[-1] for blob in shards] == [
        "00002.json.bz2",
        "00010.json.bz2",
    ]


def _shard_get(chunk: bytes = b"x" * 1024):
    """Build a session.get side effect that streams one chunk per shard."""

    def _get(url, *args, **kwargs):
        resp = MagicMock()
        resp.__enter__.return_value = resp
        resp.iter_content.return_value = [chunk]
        resp.raise_for_status.return_value = None
        return resp

    return _get


def _head(size: int | None):
    """Build a session.head side effect reporting a Content-Length (or none)."""
    resp = MagicMock()
    resp.headers = {} if size is None else {"Content-Length": str(size)}
    resp.raise_for_status.return_value = None
    return resp


def _recording_writer(sink: dict[str, bytes], name: str) -> MagicMock:
    """Build a BlobWriter stand-in that records writes and returns byte counts."""
    sink[name] = b""

    def _write(chunk: bytes) -> int:
        sink[name] += chunk
        return len(chunk)

    writer = MagicMock()
    writer.write.side_effect = _write
    return writer


def _writer_ctx(sink: dict[str, bytes], name: str) -> MagicMock:
    """Wrap a recording writer in the context manager blob.open() returns."""
    ctx = MagicMock()
    ctx.__enter__.return_value = _recording_writer(sink, name)
    ctx.__exit__.return_value = False
    return ctx


def _recording_bucket(bucket: MagicMock) -> dict[str, bytes]:
    """Make bucket.blob() record everything written, keyed by object name."""
    written: dict[str, bytes] = {}
    bucket.blob.side_effect = lambda name, chunk_size=None: MagicMock(
        open=MagicMock(return_value=_writer_ctx(written, name))
    )
    return written


@pytest.mark.asyncio
async def test_stream_dump_to_gcs_writes_one_object_per_shard(gcs_client, session):
    """Copy each shard into its own object, then publish the success marker."""
    chunk = b"x" * 1024
    session.get.side_effect = _shard_get(chunk)
    session.head.return_value = _head(len(chunk))

    bucket = gcs_client.bucket.return_value
    bucket.get_blob.return_value = None  # nothing copied yet
    written = _recording_bucket(bucket)
    fm = _file_manager(gcs_client)

    index_url = _index_url("20240401")
    await fm._stream_dump_to_gcs([f"{index_url}{name}" for name in _shards("20240401", 3)])

    prefix = "frwiki-20240401-cirrussearch-content"
    shard_objects = {name: body for name, body in written.items() if name.endswith(".bz2")}
    assert set(shard_objects) == {
        f"{prefix}/frwiki_content-20240401-00000.json.bz2",
        f"{prefix}/frwiki_content-20240401-00001.json.bz2",
        f"{prefix}/frwiki_content-20240401-00002.json.bz2",
    }
    assert all(body == chunk for body in shard_objects.values())
    # The marker is written last, and only once every shard has landed.
    bucket.blob.assert_any_call(f"{prefix}/{SUCCESS_MARKER}")


@pytest.mark.asyncio
async def test_stream_dump_to_gcs_skips_shards_already_copied(gcs_client, session):
    """Skip a shard already on GCS at its upstream size, so a retry resumes."""
    chunk = b"x" * 1024
    session.get.side_effect = _shard_get(chunk)
    session.head.return_value = _head(len(chunk))

    bucket = gcs_client.bucket.return_value
    prefix = "frwiki-20240401-cirrussearch-content"
    already = f"{prefix}/frwiki_content-20240401-00000.json.bz2"

    def _get_blob(name):
        # Shard 0 landed on a previous attempt at the right size; shard 1 did not.
        return _gcs_blob(name, size=len(chunk)) if name == already else None

    bucket.get_blob.side_effect = _get_blob
    written = _recording_bucket(bucket)
    fm = _file_manager(gcs_client)

    index_url = _index_url("20240401")
    await fm._stream_dump_to_gcs([f"{index_url}{name}" for name in _shards("20240401", 2)])

    # Only the missing shard was fetched and written.
    shard_objects = [name for name in written if name.endswith(".bz2")]
    assert shard_objects == [f"{prefix}/frwiki_content-20240401-00001.json.bz2"]
    assert session.get.call_count == 1


@pytest.mark.asyncio
async def test_stream_dump_to_gcs_recopies_shard_of_wrong_size(gcs_client, session):
    """Re-copy a shard whose object exists but does not match upstream.

    A failed write can still finalize a truncated object, so size is what decides.
    """
    chunk = b"x" * 1024
    session.get.side_effect = _shard_get(chunk)
    session.head.return_value = _head(len(chunk))

    bucket = gcs_client.bucket.return_value
    bucket.get_blob.side_effect = lambda name: _gcs_blob(name, size=7)  # truncated
    written = _recording_bucket(bucket)
    fm = _file_manager(gcs_client)

    index_url = _index_url("20240401")
    await fm._stream_dump_to_gcs([f"{index_url}{name}" for name in _shards("20240401", 1)])

    assert session.get.call_count == 1
    assert [b for n, b in written.items() if n.endswith(".bz2")] == [chunk]


@pytest.mark.asyncio
async def test_stream_dump_to_gcs_copies_when_size_unknown(gcs_client, session):
    """Copy shards even when HEAD gives no Content-Length to report against."""
    chunk = b"x" * 512
    session.get.side_effect = _shard_get(chunk)
    session.head.return_value = _head(None)

    bucket = gcs_client.bucket.return_value
    bucket.get_blob.return_value = None
    written = _recording_bucket(bucket)
    fm = _file_manager(gcs_client)

    index_url = _index_url("20240401")
    await fm._stream_dump_to_gcs([f"{index_url}{name}" for name in _shards("20240401", 1)])

    assert [b for n, b in written.items() if n.endswith(".bz2")] == [chunk]


@pytest.mark.asyncio
async def test_stream_dump_to_gcs_copies_when_head_fails(gcs_client, session, caplog):
    """Fall back to copying without progress reporting when HEAD errors.

    An unknown size also disables the resume check, so the shard is re-copied rather
    than wrongly assumed complete.
    """
    chunk = b"x" * 256
    session.get.side_effect = _shard_get(chunk)
    session.head.side_effect = ConnectionError("Simulated HEAD failure")

    bucket = gcs_client.bucket.return_value
    bucket.get_blob.return_value = _gcs_blob("already-there", size=999)
    written = _recording_bucket(bucket)
    fm = _file_manager(gcs_client)

    index_url = _index_url("20240401")
    await fm._stream_dump_to_gcs([f"{index_url}{name}" for name in _shards("20240401", 1)])

    assert [b for n, b in written.items() if n.endswith(".bz2")] == [chunk]
    assert "Could not determine size" in caplog.text


@pytest.mark.asyncio
async def test_stream_dump_to_gcs_raises_and_skips_marker_on_failure(gcs_client, session):
    """Surface the failure and leave the snapshot unmarked, so it is not indexed."""
    session.head.return_value = _head(1024)
    session.get.side_effect = ConnectionError("Simulated download failure")

    bucket = gcs_client.bucket.return_value
    bucket.get_blob.return_value = None
    fm = _file_manager(gcs_client)

    index_url = _index_url("20240401")
    with pytest.raises(WikipediaFilemanagerError, match="Failed to copy shard"):
        await fm._stream_dump_to_gcs([f"{index_url}{name}" for name in _shards("20240401", 2)])

    prefix = "frwiki-20240401-cirrussearch-content"
    assert bucket.blob.call_args_list  # shard blobs were attempted
    for call in bucket.blob.call_args_list:
        assert call.args[0] != f"{prefix}/{SUCCESS_MARKER}"


@pytest.mark.asyncio
async def test_stream_dump_to_gcs_rejects_unrecognized_shard_name(gcs_client, session):
    """Raise when a shard URL does not carry a parseable snapshot date."""
    fm = _file_manager(gcs_client)

    with pytest.raises(WikipediaFilemanagerError, match="Unrecognized shard name"):
        await fm._stream_dump_to_gcs([f"{BASE_URL}not-a-shard.json.bz2"])


@pytest.mark.asyncio
async def test_stream_latest_dump_copies_when_newer_exists(gcs_client, mocker):
    """Copy the newer snapshot and return the refreshed GCS state."""
    fm = _file_manager(gcs_client)
    newer = fm.snapshot_for(dt(2024, 4, 1))

    mocker.patch.object(FileManager, "get_latest_gcs", side_effect=[None, newer])
    mocker.patch.object(FileManager, "get_latest_dump_shards", return_value=["shard-url"])
    copy = mocker.patch.object(FileManager, "_stream_dump_to_gcs")

    result = await fm.stream_latest_dump_to_gcs()

    copy.assert_awaited_once_with(["shard-url"])
    assert result == newer


@pytest.mark.asyncio
async def test_stream_latest_dump_skips_if_up_to_date(gcs_client, mocker):
    """Do not copy anything when GCS already holds the newest snapshot."""
    fm = _file_manager(gcs_client)
    current = fm.snapshot_for(dt(2024, 4, 1))

    mocker.patch.object(FileManager, "get_latest_gcs", return_value=current)
    mocker.patch.object(FileManager, "get_latest_dump_shards", return_value=[])
    copy = mocker.patch.object(FileManager, "_stream_dump_to_gcs")

    result = await fm.stream_latest_dump_to_gcs()

    copy.assert_not_called()
    assert result == current


@pytest.mark.asyncio
async def test_stream_latest_dump_uses_caller_supplied_snapshot(gcs_client, mocker):
    """Skip re-listing GCS when the caller already knows the current snapshot."""
    fm = _file_manager(gcs_client)
    current = fm.snapshot_for(dt(2024, 4, 1))

    latest_gcs = mocker.patch.object(FileManager, "get_latest_gcs", return_value=current)
    mocker.patch.object(FileManager, "get_latest_dump_shards", return_value=[])

    result = await fm.stream_latest_dump_to_gcs(latest_gcs=current)

    latest_gcs.assert_not_called()
    assert result == current


@pytest.mark.asyncio
async def test_stream_latest_dump_when_gcs_empty(gcs_client, mocker, caplog):
    """Warn and copy from scratch when GCS holds no complete snapshot."""
    fm = _file_manager(gcs_client)
    fresh = fm.snapshot_for(dt(2024, 4, 1))

    mocker.patch.object(FileManager, "get_latest_gcs", side_effect=[None, fresh])
    mocker.patch.object(FileManager, "get_latest_dump_shards", return_value=["shard-url"])
    mocker.patch.object(FileManager, "_stream_dump_to_gcs")

    result = await fm.stream_latest_dump_to_gcs()

    assert result == fresh
    assert "No existing snapshot on GCS" in caplog.text


def test_stream_from_gcs_reads_lines_across_shards(gcs_client, mocker):
    """Chain the shards so callers still see one continuous sequence of lines."""
    shards = [
        bz2.compress(b'{"index": 1}\n{"title": "one"}\n'),
        bz2.compress(b'{"index": 2}\n{"title": "two"}\n'),
    ]
    blobs = []
    for payload in shards:
        blob = MagicMock()
        blob.open.return_value.__enter__.return_value = BytesIO(payload)
        blob.open.return_value.__exit__.return_value = False
        blobs.append(blob)

    fm = _file_manager(gcs_client)
    mocker.patch.object(FileManager, "list_gcs_shards", return_value=blobs)

    lines = list(fm.stream_from_gcs(fm.snapshot_for(dt(2024, 4, 1))))

    assert lines == [
        b'{"index": 1}\n',
        b'{"title": "one"}\n',
        b'{"index": 2}\n',
        b'{"title": "two"}\n',
    ]


def test_stream_from_gcs_raises_when_no_shards(gcs_client, mocker):
    """Raise rather than silently indexing nothing when a snapshot has no shards."""
    fm = _file_manager(gcs_client)
    mocker.patch.object(FileManager, "list_gcs_shards", return_value=[])

    with pytest.raises(WikipediaFilemanagerError, match="No shards found on GCS"):
        list(fm.stream_from_gcs(fm.snapshot_for(dt(2024, 4, 1))))


def test_snapshot_is_hashable_and_comparable(gcs_client):
    """Compare and hash Snapshot by value, since it is a frozen dataclass."""
    fm = _file_manager(gcs_client)

    first = fm.snapshot_for(dt(2024, 4, 1))
    second = fm.snapshot_for(dt(2024, 4, 1))

    assert first == second
    assert isinstance(first, Snapshot)
    assert len({first, second}) == 1
