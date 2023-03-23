"""Indexer tests"""
import datetime
import json

import freezegun
import pytest
from google.cloud.storage import Blob

from merino.jobs.wikipedia_indexer.indexer import Indexer

FROZEN_TIME = "2020-01-01"
EPOCH_FROZEN_TIME = int(
    datetime.datetime(2020, 1, 1).replace(tzinfo=datetime.timezone.utc).timestamp()
)


@pytest.fixture
def category_blocklist() -> set:
    """Return category blocklist."""
    return {"meme", "nsfw", "Anger"}


@pytest.fixture
def title_blocklist() -> set:
    """Return title blocklist."""
    return {"Bad Things"}


@pytest.fixture
def file_manager(mocker):
    """Return a mock FileManager instance."""
    fm_mock = mocker.patch("merino.jobs.wikipedia_indexer.filemanager.FileManager")
    return fm_mock.return_value


@pytest.fixture
def es_client(mocker):
    """Return a mock Elasticsearch client."""
    es_mock = mocker.patch("elasticsearch.Elasticsearch")
    return es_mock.return_value


@pytest.mark.parametrize(
    ["file_name", "version", "expected"],
    [
        ("enwiki-123-content.json", "v1", f"enwiki-123-v1-{EPOCH_FROZEN_TIME}"),
        ("foo/enwiki-123-content.json", "v1", f"enwiki-123-v1-{EPOCH_FROZEN_TIME}"),
        ("foo/bar/enwiki-123-content.json", "v1", f"enwiki-123-v1-{EPOCH_FROZEN_TIME}"),
        ("enwiki-123-content.json", "v2", f"enwiki-123-v2-{EPOCH_FROZEN_TIME}"),
    ],
)
@freezegun.freeze_time(FROZEN_TIME)
def test_get_index_name(
    file_manager,
    es_client,
    category_blocklist,
    title_blocklist,
    file_name,
    version,
    expected,
):
    """Test filename to index name parsing."""
    indexer = Indexer(
        version, category_blocklist, title_blocklist, file_manager, es_client
    )

    index_name = indexer._get_index_name(file_name)
    assert index_name == expected


@pytest.mark.parametrize(
    ["index_exists", "create_return", "expected_return", "expected_create_called"],
    [
        (False, {"acknowledged": True}, True, True),
        (False, {}, False, True),
        (True, {"acknowledged": True}, False, False),
    ],
    ids=["create_successful", "create_unsuccessful", "index_already_exists"],
)
def test_create_index(
    file_manager,
    es_client,
    category_blocklist,
    title_blocklist,
    index_exists,
    create_return,
    expected_return,
    expected_create_called,
):
    """Test create index logic."""
    es_client.indices.exists.return_value = index_exists
    es_client.indices.create.return_value = create_return

    index_name = "enwiki-123-v1"
    indexer = Indexer(
        "v1", category_blocklist, title_blocklist, file_manager, es_client
    )

    assert expected_return == indexer._create_index(index_name)
    assert expected_create_called == es_client.indices.create.called


def test_index_from_export_no_exports_available(
    file_manager, es_client, category_blocklist, title_blocklist
):
    """Test that RuntimeError is emitted."""
    file_manager.get_latest_gcs.return_value = Blob("", "bucket")
    es_client.indices.exists.return_value = False
    indexer = Indexer(
        "v1", category_blocklist, title_blocklist, file_manager, es_client
    )
    with pytest.raises(RuntimeError) as exc_info:
        indexer.index_from_export(100, "fake_alias")

    assert exc_info.value.args[0] == "No exports available on GCS"


def test_index_from_export_fail_on_existing_index(
    file_manager,
    es_client,
    category_blocklist,
    title_blocklist,
):
    """Test that Exception is emitted."""
    file_manager.get_latest_gcs.return_value = Blob(
        "foo/enwiki-20220101-cirrussearch-content.json.gz", "bar"
    )
    es_client.indices.exists.return_value = False
    es_client.indices.create.return_value = {}
    indexer = Indexer(
        "v1", category_blocklist, title_blocklist, file_manager, es_client
    )
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
    category_blocklist,
    title_blocklist,
    new_index_name,
    alias_name,
    existing_indices,
    expected_actions,
):
    """Test alias flipping logic."""
    es_client.indices.exists_alias.return_value = len(existing_indices) > 0
    es_client.indices.get_alias.return_value = existing_indices

    indexer = Indexer(
        "v1", category_blocklist, title_blocklist, file_manager, es_client
    )
    indexer._flip_alias_to_latest(new_index_name, alias_name)

    assert es_client.indices.update_aliases.called

    es_client.indices.update_aliases.assert_called_with(actions=expected_actions)


def test_index_from_export(
    file_manager,
    es_client,
    category_blocklist,
    title_blocklist,
):
    """Test full index from export flow."""
    file_manager.get_latest_gcs.return_value = Blob(
        "foo/enwiki-20220101-cirrussearch-content.json.gz", "bar"
    )

    es_client.bulk.return_value = {
        "acknowledged": True,
        "errors": False,
        "items": [{"id": 1000}],
    }
    es_client.indices.exists.return_value = False
    es_client.indices.create.return_value = {"acknowledged": True}

    operation = {"index": {"_type": "doc", "_id": "1000"}}
    document = {
        "title": "Hercule Poirot",
        "text_bytes": 1000,
        "incoming_links": 10,
        "popularity_score": 0.0003,
        "create_timestamp": "2001-06-10T22:29:58Z",
        "page_id": 1000,
    }

    inputs = [
        json.dumps(operation),
        json.dumps(document),
    ]

    file_manager.stream_from_gcs.return_value = (input for input in inputs)
    indexer = Indexer(
        "v1", category_blocklist, title_blocklist, file_manager, es_client
    )

    indexer.index_from_export(1, "enwiki")

    # es_client.bulk.assert_called_once()
    es_client.indices.refresh.assert_called_once()
    es_client.indices.update_aliases.assert_called_once()


def test_index_from_export_with_category_blocklist_content_filter(
    file_manager,
    es_client,
    category_blocklist,
    title_blocklist,
):
    """Test content moderation removes blocked categories from category blocklist."""
    file_manager.get_latest_gcs.return_value = Blob(
        "foo/enwiki-20220101-cirrussearch-content.json.gz", "bar"
    )

    def check_bulk_side_effect(operations):
        """Use a side effect to test that we send exactly 2 lines to bulk operation
        (ie. one index line, one document line).
        The operations list is mutable, so we need to check that the contents
        are in place at the time of call.
        """
        assert len(operations) == 2
        return {
            "acknowledged": True,
            "errors": False,
            "items": [{"id": 1000}],
        }

    es_client.bulk.side_effect = check_bulk_side_effect
    es_client.indices.exists.return_value = False
    es_client.indices.create.return_value = {"acknowledged": True}

    operation0 = {"index": {"_type": "doc", "_id": "1000"}}
    document0 = {
        "title": "Hercule Poirot",
        "text_bytes": 1000,
        "incoming_links": 10,
        "popularity_score": 0.0003,
        "create_timestamp": "2001-06-10T22:29:58Z",
        "page_id": 1000,
        "category": ["fiction"],
    }
    operation_filtered_out = {"index": {"_type": "doc", "_id": "1001"}}
    document_filtered_out = {
        "title": "Nyan-cat",
        "text_bytes": 1000,
        "incoming_links": 10,
        "popularity_score": 0.0003,
        "create_timestamp": "2001-06-10T22:29:58Z",
        "page_id": 1000,
        "category": ["meme"],
    }

    file_manager.stream_from_gcs.return_value = [
        json.dumps(operation0),
        json.dumps(document0),
        json.dumps(operation_filtered_out),
        json.dumps(document_filtered_out),
    ]

    indexer = Indexer(
        "v1", category_blocklist, title_blocklist, file_manager, es_client
    )

    indexer.index_from_export(1, "enwiki")

    es_client.bulk.assert_called_once()


def test_index_from_export_with_title_blocklist_content_filter(
    file_manager,
    es_client,
    category_blocklist,
    title_blocklist,
):
    """Test content moderation removes blocked categories from title blocklist.
    Also verifies that matching results are not case sensitive, given a title.
    """
    file_manager.get_latest_gcs.return_value = Blob(
        "foo/enwiki-20220101-cirrussearch-content.json.gz", "bar"
    )

    def check_bulk_side_effect(operations):
        """Use a side effect to test that we send exactly 2 lines to bulk operation
        (ie. one index line, one document line).
        The operations list is mutable, so we need to check that the contents
        are in place at the time of call.
        """
        assert len(operations) == 2
        return {
            "acknowledged": True,
            "errors": False,
            "items": [{"id": 1000}],
        }

    es_client.bulk.side_effect = check_bulk_side_effect
    es_client.indices.exists.return_value = False
    es_client.indices.create.return_value = {"acknowledged": True}

    operation0 = {"index": {"_type": "doc", "_id": "1000"}}
    document0 = {
        "title": "Hercule Poirot",
        "text_bytes": 1000,
        "incoming_links": 10,
        "popularity_score": 0.0003,
        "create_timestamp": "2001-06-10T22:29:58Z",
        "page_id": 1000,
        "category": ["fiction"],
    }
    operation_filtered_out = {"index": {"_type": "doc", "_id": "1001"}}
    document_filtered_out = {
        "title": "bad things",
        "text_bytes": 1000,
        "incoming_links": 10,
        "popularity_score": 0.0003,
        "create_timestamp": "2001-06-10T22:29:58Z",
        "page_id": 1000,
        "category": ["bad"],
    }

    inputs = [
        json.dumps(operation0),
        json.dumps(document0),
        json.dumps(operation_filtered_out),
        json.dumps(document_filtered_out),
    ]

    file_manager.stream_from_gcs.return_value = (input for input in inputs)
    indexer = Indexer(
        "v1", category_blocklist, title_blocklist, file_manager, es_client
    )

    indexer.index_from_export(1, "enwiki")

    es_client.bulk.assert_called_once()
