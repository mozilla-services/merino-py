"""Indexer tests"""

import datetime
import json
import logging
from unittest.mock import call as mocker_call

import freezegun
import pytest
from merino.jobs.wikipedia_indexer.filemanager import Snapshot
from merino.jobs.wikipedia_indexer.indexer import Indexer
from merino.search.elastic import ElasticSearchAdapter

FROZEN_TIME = "2020-01-01"
SNAPSHOT = Snapshot(
    name="enwiki-20220101-cirrussearch-content",
    date=datetime.datetime(2022, 1, 1),
    prefix="bar/enwiki-20220101-cirrussearch-content",
)
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
    fm = fm_mock.return_value
    fm.language = "en"
    return fm


@pytest.fixture
def es_adapter(mocker):
    """Return a mock ElasticSearchAdapter."""
    adapter_mock = mocker.Mock(spec=ElasticSearchAdapter)
    # Defaults so the lifecycle sweep after the alias flip has iterable results.
    adapter_mock.get_indices_for_alias.return_value = []
    adapter_mock.get_index_lifecycle_policies.return_value = {}
    return adapter_mock


@pytest.fixture
def indexer(file_manager, es_adapter, category_blocklist, title_blocklist):
    """Return a mock indexer instance"""
    return Indexer("v1", category_blocklist, title_blocklist, file_manager, es_adapter)


@pytest.mark.parametrize(
    ["file_name", "version", "expected"],
    [
        ("enwiki-123-content.json", "v1", f"enwiki-123-v1-{EPOCH_FROZEN_TIME}"),
        ("foo/plwiki-123-content.json", "v1", f"plwiki-123-v1-{EPOCH_FROZEN_TIME}"),
        ("foo/bar/dewiki-123-content.json", "v1", f"dewiki-123-v1-{EPOCH_FROZEN_TIME}"),
        ("frwiki-123-content.json", "v2", f"frwiki-123-v2-{EPOCH_FROZEN_TIME}"),
    ],
)
@freezegun.freeze_time(FROZEN_TIME)
def test_get_index_name(
    file_manager,
    es_adapter,
    category_blocklist,
    title_blocklist,
    file_name,
    version,
    expected,
):
    """Test filename to index name parsing."""
    indexer = Indexer(version, category_blocklist, title_blocklist, file_manager, es_adapter)

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
    es_adapter,
    category_blocklist,
    title_blocklist,
    index_exists,
    create_return,
    expected_return,
    expected_create_called,
):
    """Test create index logic."""
    es_adapter.index_exists.return_value = index_exists
    es_adapter.create_index.return_value = create_return.get("acknowledged", False)

    index_name = "enwiki-123-v1"
    indexer = Indexer("v1", category_blocklist, title_blocklist, file_manager, es_adapter)

    assert expected_return == indexer._create_index(index_name)
    assert expected_create_called == es_adapter.create_index.called


def test_index_from_export_no_exports_available(
    file_manager, es_adapter, category_blocklist, title_blocklist
):
    """Test that RuntimeError is emitted."""
    file_manager.get_latest_gcs.return_value = None
    file_manager.language = "en"
    es_adapter.index_exists.return_value = False
    indexer = Indexer("v1", category_blocklist, title_blocklist, file_manager, es_adapter)
    with pytest.raises(RuntimeError) as exc_info:
        indexer.index_from_export(100, "fake_alias")

    assert exc_info.value.args[0] == "No exports available on GCS for en"


def test_index_from_export_fail_on_existing_index(
    file_manager,
    es_adapter,
    category_blocklist,
    title_blocklist,
):
    """Test that Exception is emitted."""
    file_manager.get_latest_gcs.return_value = SNAPSHOT
    es_adapter.index_exists.return_value = False
    es_adapter.create_index.return_value = False
    indexer = Indexer("v1", category_blocklist, title_blocklist, file_manager, es_adapter)
    with pytest.raises(Exception) as exc_info:
        indexer.index_from_export(100, "fake_alias")

    assert exc_info.value.args[0] == "Could not create the index"


@pytest.mark.parametrize(
    [
        "new_index_name",
        "alias_name",
        "existing_indices",
        "expected_actions",
    ],
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
    es_adapter,
    category_blocklist,
    title_blocklist,
    new_index_name,
    alias_name,
    existing_indices,
    expected_actions,
):
    """Test alias flipping logic."""
    es_adapter.alias_exists.return_value = len(existing_indices) > 0
    es_adapter.get_indices_for_alias.return_value = existing_indices

    indexer = Indexer("v1", category_blocklist, title_blocklist, file_manager, es_adapter)
    indexer._flip_alias_to_latest(new_index_name, alias_name)

    assert es_adapter.update_aliases.called

    es_adapter.update_aliases.assert_called_with(actions=expected_actions)


@freezegun.freeze_time(FROZEN_TIME)
def test_index_from_export(
    file_manager,
    es_adapter,
    category_blocklist,
    title_blocklist,
):
    """Test full index from export flow."""
    file_manager.get_latest_gcs.return_value = SNAPSHOT

    es_adapter.bulk.return_value = {
        "acknowledged": True,
        "errors": False,
        "items": [{"id": 1000}],
    }
    es_adapter.index_exists.return_value = False
    es_adapter.create_index.return_value = True
    es_adapter.alias_exists.return_value = False

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
    indexer = Indexer("v1", category_blocklist, title_blocklist, file_manager, es_adapter)

    indexer.index_from_export(1, "enwiki")

    es_adapter.bulk.assert_called_once()
    es_adapter.refresh_index.assert_called_once()
    es_adapter.update_aliases.assert_called_once()
    es_adapter.set_index_lifecycle_policy.assert_called_once_with(
        index=f"enwiki-20220101-v1-{EPOCH_FROZEN_TIME}", policy="enwiki_policy"
    )


@freezegun.freeze_time(FROZEN_TIME)
def test_index_from_export_applies_active_policy_before_flipping_alias(
    file_manager,
    es_adapter,
    category_blocklist,
    title_blocklist,
    mocker,
):
    """Test that the new index is never exposed under the alias while it still
    carries a policy that could delete it.
    """
    file_manager.get_latest_gcs.return_value = SNAPSHOT

    es_adapter.bulk.return_value = {"acknowledged": True, "errors": False, "items": [{"id": 1000}]}
    es_adapter.index_exists.return_value = False
    es_adapter.create_index.return_value = True
    es_adapter.alias_exists.return_value = False

    calls = mocker.Mock()
    calls.attach_mock(es_adapter.set_index_lifecycle_policy, "set_policy")
    calls.attach_mock(es_adapter.update_aliases, "update_aliases")

    inputs = [
        json.dumps({"index": {"_type": "doc", "_id": "1000"}}),
        json.dumps({"title": "Paris", "page_id": 1000, "category": ["cities"]}),
    ]
    file_manager.stream_from_gcs.return_value = (input for input in inputs)
    indexer = Indexer("v1", category_blocklist, title_blocklist, file_manager, es_adapter)

    indexer.index_from_export(1, "enwiki-{version}")

    # Ordering is important here
    assert [call[0] for call in calls.mock_calls] == ["set_policy", "update_aliases"]


@freezegun.freeze_time(FROZEN_TIME)
def test_index_from_export_demotes_superseded_indices_to_backup_policy(
    file_manager,
    es_adapter,
    category_blocklist,
    title_blocklist,
):
    """Test that indices no longer served by the alias get the backup policy, and
    that the live index and already-demoted indices are left alone.
    """
    file_manager.get_latest_gcs.return_value = SNAPSHOT
    new_index = f"enwiki-20220101-v1-{EPOCH_FROZEN_TIME}"

    es_adapter.bulk.return_value = {"acknowledged": True, "errors": False, "items": [{"id": 1000}]}
    es_adapter.index_exists.return_value = False
    es_adapter.create_index.return_value = True
    es_adapter.alias_exists.return_value = False
    # Post-flip the alias resolves to the just-built index
    es_adapter.get_indices_for_alias.return_value = [new_index]
    es_adapter.get_index_lifecycle_policies.return_value = {
        new_index: "enwiki_policy",
        "enwiki-20211201-v1-100": "enwiki_policy",
        "enwiki-20211101-v1-99": "enwiki_backup_policy",
        "enwiki-20211001-v1-98": None,
    }

    inputs = [
        json.dumps({"index": {"_type": "doc", "_id": "1000"}}),
        json.dumps({"title": "Paris", "page_id": 1000, "category": ["cities"]}),
    ]
    file_manager.stream_from_gcs.return_value = (input for input in inputs)
    indexer = Indexer("v1", category_blocklist, title_blocklist, file_manager, es_adapter)

    indexer.index_from_export(1, "enwiki-{version}")

    es_adapter.get_index_lifecycle_policies.assert_called_once_with(index="enwiki-*-v1-*")
    assert es_adapter.set_index_lifecycle_policy.call_args_list == [
        # The active index, applied before the flip.
        mocker_call(index=new_index, policy="enwiki_policy"),
        # Superseded, and not already on the backup policy.
        mocker_call(index="enwiki-20211201-v1-100", policy="enwiki_backup_policy"),
        mocker_call(index="enwiki-20211001-v1-98", policy="enwiki_backup_policy"),
    ]


@pytest.mark.parametrize("language", ["en", "fr", "de", "it", "pl"])
def test_backup_lifecycle_policies_are_language_scoped(
    file_manager,
    es_adapter,
    category_blocklist,
    title_blocklist,
    language,
):
    """Test that policy names and the discovery pattern track the language."""
    file_manager.language = language
    es_adapter.get_indices_for_alias.return_value = [f"{language}wiki-1-v1-2"]
    es_adapter.get_index_lifecycle_policies.return_value = {f"{language}wiki-1-v1-1": None}

    indexer = Indexer("v1", category_blocklist, title_blocklist, file_manager, es_adapter)
    indexer._apply_backup_lifecycle_policies(f"{language}wiki-v1")

    es_adapter.get_index_lifecycle_policies.assert_called_once_with(index=f"{language}wiki-*-v1-*")
    es_adapter.set_index_lifecycle_policy.assert_called_once_with(
        index=f"{language}wiki-1-v1-1", policy=f"{language}wiki_backup_policy"
    )


def test_index_from_export_with_category_blocklist_content_filter(
    file_manager,
    es_adapter,
    category_blocklist,
    title_blocklist,
):
    """Test content moderation removes blocked categories from category blocklist."""
    file_manager.get_latest_gcs.return_value = SNAPSHOT

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

    es_adapter.bulk.side_effect = check_bulk_side_effect
    es_adapter.index_exists.return_value = False
    es_adapter.create_index.return_value = True
    es_adapter.alias_exists.return_value = False

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

    inputs = [
        json.dumps(operation0),
        json.dumps(document0),
        json.dumps(operation_filtered_out),
        json.dumps(document_filtered_out),
    ]

    file_manager.stream_from_gcs.return_value = (input for input in inputs)
    indexer = Indexer("v1", category_blocklist, title_blocklist, file_manager, es_adapter)

    indexer.index_from_export(1, "enwiki")

    es_adapter.bulk.assert_called_once()


def test_index_from_export_with_title_blocklist_content_filter(
    file_manager,
    es_adapter,
    category_blocklist,
    title_blocklist,
):
    """Test content moderation removes blocked categories from title blocklist.
    Also verifies that matching results are not case sensitive, given a title.
    """
    file_manager.get_latest_gcs.return_value = SNAPSHOT

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

    es_adapter.bulk.side_effect = check_bulk_side_effect
    es_adapter.index_exists.return_value = False
    es_adapter.create_index.return_value = True
    es_adapter.alias_exists.return_value = False

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
        "title": "Bad things",
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
    indexer = Indexer("v1", category_blocklist, title_blocklist, file_manager, es_adapter)

    indexer.index_from_export(1, "enwiki")

    es_adapter.bulk.assert_called_once()


def test_index_from_export_filters_redirects(
    file_manager,
    es_adapter,
    category_blocklist,
    title_blocklist,
):
    """Test that redirect documents are not indexed."""
    file_manager.get_latest_gcs.return_value = SNAPSHOT

    def check_bulk_side_effect(operations):
        """Use a side effect to check only the primary document reaches bulk.
        The operations list is mutable, so the contents must be checked at call time.
        """
        assert len(operations) == 2
        assert operations[1]["title"] == "Paris"
        return {
            "acknowledged": True,
            "errors": False,
            "items": [{"id": 1000}],
        }

    es_adapter.bulk.side_effect = check_bulk_side_effect
    es_adapter.index_exists.return_value = False
    es_adapter.create_index.return_value = True
    es_adapter.alias_exists.return_value = False

    operation0 = {"index": {"_type": "doc", "_id": "1000"}}
    document0 = {
        "title": "Paris",
        "text_bytes": 1000,
        "incoming_links": 10,
        "popularity_score": 0.0003,
        "create_timestamp": "2001-06-10T22:29:58Z",
        "page_id": 1000,
        "page_type": "primary",
        "category": ["cities"],
    }
    operation_filtered_out = {"index": {"_type": "doc", "_id": "1001"}}
    document_filtered_out = {
        "title": "Paris, France",
        "text_bytes": 1000,
        "incoming_links": 10,
        "popularity_score": 0.0003,
        "create_timestamp": "2001-06-10T22:29:58Z",
        "page_id": 1001,
        "page_type": "redirect",
        "category": ["cities"],
    }

    inputs = [
        json.dumps(operation0),
        json.dumps(document0),
        json.dumps(operation_filtered_out),
        json.dumps(document_filtered_out),
    ]

    file_manager.stream_from_gcs.return_value = (input for input in inputs)
    indexer = Indexer("v1", category_blocklist, title_blocklist, file_manager, es_adapter)

    indexer.index_from_export(1, "enwiki")

    es_adapter.bulk.assert_called_once()


def test_index_from_export_keeps_documents_without_a_page_type(
    file_manager,
    es_adapter,
    category_blocklist,
    title_blocklist,
):
    """Test that a document with no page type is still indexed."""
    file_manager.get_latest_gcs.return_value = SNAPSHOT

    es_adapter.bulk.return_value = {
        "acknowledged": True,
        "errors": False,
        "items": [{"id": 1000}],
    }
    es_adapter.index_exists.return_value = False
    es_adapter.create_index.return_value = True
    es_adapter.alias_exists.return_value = False

    inputs = [
        json.dumps({"index": {"_type": "doc", "_id": "1000"}}),
        json.dumps(
            {
                "title": "Paris",
                "text_bytes": 1000,
                "incoming_links": 10,
                "popularity_score": 0.0003,
                "create_timestamp": "2001-06-10T22:29:58Z",
                "page_id": 1000,
                "category": ["cities"],
            }
        ),
    ]

    file_manager.stream_from_gcs.return_value = (input for input in inputs)
    indexer = Indexer("v1", category_blocklist, title_blocklist, file_manager, es_adapter)

    indexer.index_from_export(1, "enwiki")

    es_adapter.bulk.assert_called_once()


def _set_queue(indexer, n=1):
    # queue is [op, doc, op, doc, ...]
    indexer.queue.clear()
    for i in range(n):
        indexer.queue.append({"index": {"_index": "test-idx", "_id": str(i)}})
        indexer.queue.append({"title": f"Doc {i}"})


def test_index_docs_raises_with_first_failing_item(indexer, es_adapter, caplog):
    """Test that when errors=True, raise with the first item that actually failed, not just items[0]."""
    _set_queue(indexer, n=2)

    # first item is a success, second item is a failure
    # The ElasticSearchAdapter.bulk raises RuntimeError when errors=True
    es_adapter.bulk.side_effect = RuntimeError(
        "Bulk failed. First error: {'action': 'index', 'status': 400, 'index': 'test-idx', "
        "'id': '1', 'error': {'type': 'mapper_parsing_exception', 'reason': 'failed to parse field [suggest]'}}"
    )

    with caplog.at_level(logging.ERROR):
        with pytest.raises(RuntimeError) as exc:
            indexer._index_docs(force=True)

    msg = str(exc.value)
    assert "Bulk failed" in msg
    assert "mapper_parsing_exception" in msg
    assert indexer.queue == []


def test_index_docs_handles_non_index_actions(indexer, es_adapter):
    """Test that index_docs works when ES returns actions like 'update'"""
    _set_queue(indexer, n=1)
    # The ElasticSearchAdapter.bulk raises RuntimeError when errors=True
    es_adapter.bulk.side_effect = RuntimeError(
        "Bulk failed. First error: {'action': 'update', 'status': 404, 'index': 'test-idx', "
        "'id': '42', 'error': {'type': 'document_missing_exception', 'reason': '[42]: document missing'}}"
    )
    with pytest.raises(RuntimeError) as exc:
        indexer._index_docs(force=True)
    assert "document_missing_exception" in str(exc.value)
    assert indexer.queue == []


def test_index_docs_success_returns_item_count(indexer, es_adapter):
    """Test that when errors=False, return count and do not raise."""
    _set_queue(indexer, n=3)
    es_adapter.bulk.return_value = {
        "took": 5,
        "errors": False,
        "items": [
            {"index": {"_index": "test-idx", "_id": "0", "status": 201}},
            {"index": {"_index": "test-idx", "_id": "1", "status": 201}},
            {"index": {"_index": "test-idx", "_id": "2", "status": 201}},
        ],
    }
    count = indexer._index_docs(force=True)
    assert count == 3
    assert indexer.queue == []
