"""Indexer tests"""
import json

import pytest
from google.cloud.storage import Blob

from merino.jobs.wikipedia_indexer.indexer import Indexer


@pytest.fixture
def file_manager(mocker):
    """Return a mock FileManager instance"""
    fm_mock = mocker.patch("merino.jobs.wikipedia_indexer.filemanager.FileManager")
    return fm_mock.return_value


@pytest.fixture
def es_client(mocker):
    """Return a mock Elasticsearch client"""
    es_mock = mocker.patch("elasticsearch.Elasticsearch")
    return es_mock.return_value


@pytest.mark.parametrize(
    ["file_name", "version", "expected"],
    [
        ("enwiki-123-content.json", "v1", "enwiki-123-v1"),
        ("foo/enwiki-123-content.json", "v1", "enwiki-123-v1"),
        ("foo/bar/enwiki-123-content.json", "v1", "enwiki-123-v1"),
        ("enwiki-123-content.json", "v2", "enwiki-123-v2"),
    ],
)
def test_get_index_name(file_manager, es_client, file_name, version, expected):
    """Test filename to index name parsing"""
    indexer = Indexer(version, file_manager, es_client)

    index_name = indexer._get_index_name(file_name)
    assert index_name == expected


def test_ensure_index(file_manager, es_client):
    """Test ensure index logic"""
    es_client.indices.exists.return_value = False

    index_name = "enwiki-123-v1"
    indexer = Indexer("v1", file_manager, es_client)
    indexer._ensure_index(index_name)

    assert es_client.indices.create.called


def test_index_from_export_no_exports_available(file_manager, es_client):
    """Test that RuntimeError is emitted"""
    file_manager.get_latest_gcs.return_value = Blob("", "bucket")
    indexer = Indexer("v1", file_manager, es_client)
    with pytest.raises(RuntimeError) as exc_info:
        indexer.index_from_export(100, "fake_alias")

    assert exc_info.value.args[0] == "No exports available on gcs"


def test_index_from_export_fail_on_existing_index(file_manager, es_client):
    """Test that Exception is emitted"""
    file_manager.get_latest_gcs.return_value = Blob(
        "foo/enwiki-20220101-cirrussearch-content.json.gz", "bar"
    )
    es_client.indices.exists.return_value = False
    es_client.indices.create.return_value = {}
    indexer = Indexer("v1", file_manager, es_client)
    with pytest.raises(Exception) as exc_info:
        indexer.index_from_export(100, "fake_alias")

    assert exc_info.value.args[0] == "Could not create the index"


@pytest.mark.parametrize(
    ["new_index_name", "alias_name", "existing_indices", "expected_actions"],
    [
        (
            "enwiki-123",
            "enwiki",
            ["enwiki-345"],
            [
                {"add": {"index": "enwiki-123", "alias": "enwiki"}},
                {"remove": {"index": "enwiki-345", "alias": "enwiki"}},
            ],
        ),
        (
            "enwiki-123",
            "enwiki-{version}",
            ["enwiki-345", "enwiki-678"],
            [
                {"add": {"index": "enwiki-123", "alias": "enwiki-v1"}},
                {"remove": {"index": "enwiki-345", "alias": "enwiki-v1"}},
                {"remove": {"index": "enwiki-678", "alias": "enwiki-v1"}},
            ],
        ),
        (
            "enwiki-123",
            "enwiki-{version}",
            [],
            [
                {"add": {"index": "enwiki-123", "alias": "enwiki-v1"}},
            ],
        ),
    ],
)
def test_flip_alias(
    file_manager,
    es_client,
    new_index_name,
    alias_name,
    existing_indices,
    expected_actions,
):
    """Test alias flipping logic"""
    es_client.indices.exists_alias.return_value = len(existing_indices) > 0
    es_client.indices.get_alias.return_value = existing_indices

    indexer = Indexer("v1", file_manager, es_client)
    indexer._flip_alias_to_latest(new_index_name, alias_name)

    assert es_client.indices.update_aliases.called

    es_client.indices.update_aliases.assert_called_with(actions=expected_actions)


def test_index_from_export(file_manager, es_client):
    """Test full index from export flow"""
    file_manager.get_latest_gcs.return_value = Blob(
        "foo/enwiki-20220101-cirrussearch-content.json.gz", "bar"
    )

    es_client.bulk.return_value = {
        "acknowledged": True,
        "errors": False,
        "items": [{"id": 1000}],
    }
    es_client.indices.exists.return_value = True

    operation = {"index": {"_type": "doc", "_id": "1000"}}
    document = {
        "title": "Hercule Poirot",
        "text_bytes": 1000,
        "incoming_links": 10,
        "popularity_score": 0.0003,
        "create_timestamp": "2001-06-10T22:29:58Z",
        "page_id": 1000,
    }

    file_manager._stream_from_gcs.return_value = [
        json.dumps(operation),
        json.dumps(document),
    ]

    indexer = Indexer("v1", file_manager, es_client)

    indexer.index_from_export(1, "enwiki")

    es_client.bulk.assert_called_once()
    es_client.indices.refresh.assert_called_once()
    es_client.indices.update_aliases.assert_called_once()
