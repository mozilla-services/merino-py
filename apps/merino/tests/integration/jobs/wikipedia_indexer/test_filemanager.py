"""FileManager tests"""

import bz2
from datetime import datetime as dt
from io import BytesIO
from unittest.mock import MagicMock

import pytest

from merino.jobs.wikipedia_indexer.filemanager import (
    SUCCESS_MARKER,
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
    """Test snapshot traversal and date comparisons of get_latest_dump_shards."""
    shard_names = [f"enwiki_content-{snapshot_date}-{i:05d}.json.bz2" for i in range(3)]

    requests_mock.get(BASE_URL, text=_links([f"{snapshot_date}/"]))  # nosec
    requests_mock.get(  # nosec
        _index_url(snapshot_date), text=_links([*shard_names, SUCCESS_MARKER])
    )

    file_manager = FileManager("foo/bar", "a-project", BASE_URL, "en")
    latest_gcs = file_manager.snapshot_for(dt.strptime(gcs_date, "%Y%m%d"))

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
        text=_links(["enwiki_content-20220101-00000.json.bz2", SUCCESS_MARKER]),
    )

    file_manager = FileManager("foo/bar", "a-project", BASE_URL, "en")

    shard_urls = file_manager.get_latest_dump_shards(None)

    assert shard_urls == [f"{_index_url('20220101')}enwiki_content-20220101-00000.json.bz2"]


@pytest.mark.asyncio
async def test_stream_dump_to_gcs_copies_every_shard(requests_mock, mock_gcs_client):
    """Copy the shards to GCS as separate objects, over the real HTTP stack."""
    shard_names = [f"enwiki_content-20220101-{i:05d}.json.bz2" for i in range(3)]
    body = b"chunk1chunk2chunk3"
    for name in shard_names:
        requests_mock.head(f"{_index_url('20220101')}{name}", headers={"Content-Length": "18"})  # nosec
        requests_mock.get(f"{_index_url('20220101')}{name}", content=body)  # nosec

    bucket = mock_gcs_client.bucket.return_value
    bucket.get_blob.return_value = None
    written: dict[str, bytes] = {}

    def _blob(name, chunk_size=None):
        buffer = BytesIO()
        blob = MagicMock()
        blob.open.return_value.__enter__.return_value = buffer
        blob.open.return_value.__exit__.side_effect = lambda *a: written.update(
            {name: buffer.getvalue()}
        )
        return blob

    bucket.blob.side_effect = _blob

    file_manager = FileManager("foo/bar", "a-project", BASE_URL, "en")
    await file_manager._stream_dump_to_gcs(
        [f"{_index_url('20220101')}{name}" for name in shard_names]
    )

    prefix = "bar/enwiki-20220101-cirrussearch-content"
    assert written == {f"{prefix}/{name}": body for name in shard_names}
    # The marker is only written once every shard has landed.
    bucket.blob.assert_any_call(f"{prefix}/{SUCCESS_MARKER}")


@pytest.mark.asyncio
async def test_stream_dump_to_gcs_does_not_mark_snapshot_on_failure(
    requests_mock, mock_gcs_client
):
    """A failed shard leaves the snapshot unmarked, so the indexer skips it."""
    shard_url = f"{_index_url('20220101')}enwiki_content-20220101-00000.json.bz2"
    requests_mock.head(shard_url, headers={"Content-Length": "18"})  # nosec
    requests_mock.get(shard_url, content=b"chunk")  # nosec

    bucket = mock_gcs_client.bucket.return_value
    bucket.get_blob.return_value = None
    blob = MagicMock()
    blob.open.return_value.__enter__.return_value.write.side_effect = Exception("write failed")
    bucket.blob.return_value = blob

    file_manager = FileManager("foo/bar", "a-project", BASE_URL, "en")

    with pytest.raises(WikipediaFilemanagerError, match="Failed to copy shard"):
        await file_manager._stream_dump_to_gcs([shard_url])

    marker = "bar/enwiki-20220101-cirrussearch-content/_SUCCESS"
    assert marker not in [call.args[0] for call in bucket.blob.call_args_list]


def test_stream_from_gcs_round_trips_real_bz2(mock_gcs_client):
    """Read real multi-shard bz2 content back as one continuous line stream."""
    payloads = [
        bz2.compress(b'{"index": {"_id": "1"}}\n{"title": "one"}\n'),
        bz2.compress(b'{"index": {"_id": "2"}}\n{"title": "two"}\n'),
    ]

    blobs = []
    for i, payload in enumerate(payloads):
        blob = MagicMock()
        blob.name = (
            f"bar/enwiki-20220101-cirrussearch-content/enwiki_content-20220101-{i:05d}.json.bz2"
        )
        blob.open.return_value.__enter__.return_value = BytesIO(payload)
        blob.open.return_value.__exit__.return_value = False
        blobs.append(blob)

    mock_gcs_client.bucket.return_value.list_blobs.return_value = blobs

    file_manager = FileManager("foo/bar", "a-project", BASE_URL, "en")
    snapshot = file_manager.snapshot_for(dt(2022, 1, 1))

    assert list(file_manager.stream_from_gcs(snapshot)) == [
        b'{"index": {"_id": "1"}}\n',
        b'{"title": "one"}\n',
        b'{"index": {"_id": "2"}}\n',
        b'{"title": "two"}\n',
    ]
