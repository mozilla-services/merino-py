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
    # No CCR followers unless a test says otherwise.
    adapter_mock.get_shard_stats.return_value = {}
    return adapter_mock


@pytest.fixture
def indexer(file_manager, es_adapter, category_blocklist, title_blocklist):
    """Return a mock indexer instance"""
    return Indexer(
        "v1",
        category_blocklist,
        title_blocklist,
        file_manager,
        es_adapter,
        follower_discovery_period=0,
    )


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
    indexer,
    file_manager,
    es_adapter,
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

    indexer.index_from_export(1, "enwiki")

    es_adapter.bulk.assert_called_once()
    es_adapter.refresh_index.assert_called_once()
    es_adapter.update_aliases.assert_called_once()
    es_adapter.delete_index.assert_called_once_with(
        index=f"temp-enwiki-20220101-v1-{EPOCH_FROZEN_TIME}", ignore_missing=True
    )
    es_adapter.set_index_lifecycle_policy.assert_called_once_with(
        index=f"enwiki-20220101-v1-{EPOCH_FROZEN_TIME}", policy="enwiki_policy"
    )


@freezegun.freeze_time(FROZEN_TIME)
def test_index_from_export_applies_active_policy_before_flipping_alias(
    indexer,
    file_manager,
    es_adapter,
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

    indexer.index_from_export(1, "enwiki-{version}")

    # Ordering is important here
    assert [call[0] for call in calls.mock_calls] == ["set_policy", "update_aliases"]


@freezegun.freeze_time(FROZEN_TIME)
def test_index_from_export_demotes_superseded_indices_to_backup_policy(
    indexer,
    file_manager,
    es_adapter,
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
    indexer,
    file_manager,
    es_adapter,
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

    indexer.index_from_export(1, "enwiki")

    es_adapter.bulk.assert_called_once()


def test_index_from_export_with_title_blocklist_content_filter(
    indexer,
    file_manager,
    es_adapter,
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

    indexer.index_from_export(1, "enwiki")

    es_adapter.bulk.assert_called_once()


def test_index_from_export_filters_redirects(
    indexer,
    file_manager,
    es_adapter,
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

    indexer.index_from_export(1, "enwiki")

    es_adapter.bulk.assert_called_once()


def test_index_from_export_keeps_documents_without_a_page_type(
    indexer,
    file_manager,
    es_adapter,
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

    indexer.index_from_export(1, "enwiki")

    es_adapter.bulk.assert_called_once()


def _ready_to_index(file_manager, es_adapter, docs=1):
    """Set the mocks up so index_from_export gets past creating the index."""
    file_manager.get_latest_gcs.return_value = SNAPSHOT
    es_adapter.index_exists.return_value = False
    es_adapter.create_index.return_value = True
    es_adapter.alias_exists.return_value = False
    es_adapter.bulk.return_value = {"errors": False, "items": [{"id": 1000}]}

    inputs = []
    for i in range(docs):
        inputs.append(json.dumps({"index": {"_type": "doc", "_id": str(i)}}))
        inputs.append(
            json.dumps(
                {
                    "title": f"Article {i}",
                    "text_bytes": 1000,
                    "incoming_links": 10,
                    "popularity_score": 0.0003,
                    "create_timestamp": "2001-06-10T22:29:58Z",
                    "page_id": i,
                }
            )
        )
    file_manager.stream_from_gcs.return_value = (line for line in inputs)


@pytest.mark.parametrize(
    "failing_call",
    [
        "bulk",
        "refresh_index",
        "forcemerge",
        "block_writes",
        "clone_index",
        "set_index_lifecycle_policy",
        "update_aliases",
    ],
)
def test_index_from_export_discards_the_index_when_the_build_fails(
    indexer, file_manager, es_adapter, failing_call
):
    """Verify the build index and its clone, neither of which reached the alias, are
    deleted on any failure.
    """
    _ready_to_index(file_manager, es_adapter)
    getattr(es_adapter, failing_call).side_effect = RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        indexer.index_from_export(1, "enwiki-{version}")

    build_index = es_adapter.create_index.call_args.kwargs["index"]
    assert es_adapter.delete_index.call_args_list == [
        mocker_call(index=build_index.removeprefix("temp-"), ignore_missing=True),
        mocker_call(index=build_index, ignore_missing=True),
    ]


def test_index_from_export_discards_the_index_when_the_export_is_unreadable(
    indexer, file_manager, es_adapter
):
    """Verify a failure while reading the export also cleans up."""
    _ready_to_index(file_manager, es_adapter)
    file_manager.stream_from_gcs.side_effect = RuntimeError("gcs is down")

    with pytest.raises(RuntimeError, match="gcs is down"):
        indexer.index_from_export(1, "enwiki-{version}")

    es_adapter.delete_index.assert_called_with(
        index=es_adapter.create_index.call_args.kwargs["index"], ignore_missing=True
    )


def test_index_from_export_keeps_the_index_once_the_alias_has_flipped(
    indexer, file_manager, es_adapter
):
    """Verify a published index is never deleted, even if a later step fails."""
    _ready_to_index(file_manager, es_adapter)

    es_adapter.get_index_lifecycle_policies.side_effect = RuntimeError("too late")

    with pytest.raises(RuntimeError, match="too late"):
        indexer.index_from_export(1, "enwiki-{version}")

    # The flip happened, so only the temp build index is deleted.
    es_adapter.update_aliases.assert_called_once()
    es_adapter.delete_index.assert_called_once_with(
        index=es_adapter.create_index.call_args.kwargs["index"], ignore_missing=True
    )


def test_index_from_export_reports_the_original_error_when_cleanup_fails(
    indexer, file_manager, es_adapter, caplog
):
    """Verify a failed cleanup is logged but does not mask what stopped the build."""
    _ready_to_index(file_manager, es_adapter)
    es_adapter.forcemerge.side_effect = RuntimeError("forcemerge timed out")
    es_adapter.delete_index.side_effect = RuntimeError("delete also failed")

    with caplog.at_level(logging.ERROR):
        with pytest.raises(RuntimeError, match="forcemerge timed out"):
            indexer.index_from_export(1, "enwiki-{version}")

    assert any("Failed to discard unpublished index" in r.message for r in caplog.records)


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


def _shard(global_checkpoint: int, *ccr_retaining_seq_nos: int, primary: bool = True) -> dict:
    """Return one shard copy's stats with a peer recovery lease plus one CCR lease
    per follower, retaining the given sequence numbers.

    The shape mirrors a real `_stats?level=shards` response, which
    tests/integration/search/test_elastic_adapter.py checks against Elasticsearch. The
    CCR lease semantics (`source: "ccr"`, retaining the follower's global checkpoint
    + 1) need two licensed clusters, so were verified manually with
    `make docker-compose-up-ccr`.
    """
    leases = [{"id": "peer_recovery/node", "retaining_seq_no": 0, "source": "peer recovery"}]
    leases += [
        {"id": f"follower-{i}", "retaining_seq_no": seq_no, "source": "ccr"}
        for i, seq_no in enumerate(ccr_retaining_seq_nos)
    ]
    return {
        "routing": {"primary": primary},
        "seq_no": {"global_checkpoint": global_checkpoint},
        "retention_leases": {"leases": leases},
    }


class FakeClock:
    """Stands in for the indexer's monotonic clock; sleeping advances it instantly."""

    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        """Return the current fake time."""
        return self.now

    def sleep(self, seconds: float) -> None:
        """Advance the fake time without blocking."""
        self.now += seconds


@pytest.fixture
def clock(mocker) -> FakeClock:
    """Patch the indexer's clock with a FakeClock."""
    fake = FakeClock()
    mocker.patch(
        "merino.jobs.wikipedia_indexer.indexer.time.monotonic", side_effect=fake.monotonic
    )
    mocker.patch("merino.jobs.wikipedia_indexer.indexer.time.sleep", side_effect=fake.sleep)
    return fake


def test_wait_for_followers_polls_until_every_shard_catches_up(
    file_manager, es_adapter, category_blocklist, title_blocklist, clock
):
    """Test that the wait continues until all followers retain past the leader's
    global checkpoint on every shard, judging only the primary copy.
    """
    es_adapter.get_shard_stats.side_effect = [
        # Both followers behind on shard 0.
        {"0": [_shard(99, 50, 0)], "1": [_shard(42, 43, 43)]},
        # follower-1 still behind on shard 0. The replica's stale view is ignored.
        {"0": [_shard(99, 0, 0, primary=False), _shard(99, 100, 99)], "1": [_shard(42, 43, 43)]},
        # Caught up.
        {"0": [_shard(99, 100, 100)], "1": [_shard(42, 43, 43)]},
    ]
    indexer = Indexer(
        "v1",
        category_blocklist,
        title_blocklist,
        file_manager,
        es_adapter,
        follower_sync_poll_interval=7,
        follower_discovery_period=0,
    )

    indexer._wait_for_followers("enwiki-1")

    assert es_adapter.get_shard_stats.call_count == 3
    assert clock.now == 14


def test_wait_for_followers_times_out(
    file_manager, es_adapter, category_blocklist, title_blocklist, clock
):
    """Test that a follower that never catches up fails the wait."""
    es_adapter.get_shard_stats.return_value = {"0": [_shard(99, 100, 10)]}
    indexer = Indexer(
        "v1",
        category_blocklist,
        title_blocklist,
        file_manager,
        es_adapter,
        follower_sync_timeout=60,
        follower_sync_poll_interval=15,
    )

    with pytest.raises(TimeoutError, match=r"enwiki-1 did not catch up within 60s.*follower-1"):
        indexer._wait_for_followers("enwiki-1")

    assert clock.now == 60


@freezegun.freeze_time(FROZEN_TIME)
def test_index_from_export_discards_index_when_followers_time_out(
    file_manager, es_adapter, category_blocklist, title_blocklist
):
    """Test that the alias is left alone and the new index discarded when followers
    never catch up.
    """
    file_manager.get_latest_gcs.return_value = SNAPSHOT
    es_adapter.bulk.return_value = {"acknowledged": True, "errors": False, "items": [{"id": 1000}]}
    es_adapter.index_exists.return_value = False
    es_adapter.create_index.return_value = True
    es_adapter.get_shard_stats.return_value = {"0": [_shard(99, 10)]}

    inputs = [
        json.dumps({"index": {"_type": "doc", "_id": "1000"}}),
        json.dumps({"title": "Paris", "page_id": 1000, "category": ["cities"]}),
    ]
    file_manager.stream_from_gcs.return_value = (input for input in inputs)
    indexer = Indexer(
        "v1",
        category_blocklist,
        title_blocklist,
        file_manager,
        es_adapter,
        follower_sync_timeout=0,
    )

    with pytest.raises(TimeoutError):
        indexer.index_from_export(1, "enwiki-{version}")

    es_adapter.update_aliases.assert_not_called()
    assert es_adapter.delete_index.call_args_list == [
        mocker_call(index=f"enwiki-20220101-v1-{EPOCH_FROZEN_TIME}", ignore_missing=True),
        mocker_call(index=f"temp-enwiki-20220101-v1-{EPOCH_FROZEN_TIME}", ignore_missing=True),
    ]


def test_wait_for_followers_waits_out_the_discovery_period_without_followers(
    file_manager, es_adapter, category_blocklist, title_blocklist, clock
):
    """Test that an index without followers is only declared follower-free once
    auto-follow has had the discovery period to pick it up.
    """
    es_adapter.get_shard_stats.return_value = {"0": [_shard(99)]}
    indexer = Indexer(
        "v1",
        category_blocklist,
        title_blocklist,
        file_manager,
        es_adapter,
        follower_sync_poll_interval=15,
        follower_discovery_period=60,
    )

    indexer._wait_for_followers("enwiki-1")

    assert clock.now == 60


def test_wait_for_followers_waits_on_followers_found_during_discovery(
    file_manager, es_adapter, category_blocklist, title_blocklist, clock
):
    """Test that a follower that appears partway through discovery is waited on, even
    after an earlier follower is already in sync.
    """
    es_adapter.get_shard_stats.side_effect = [
        {"0": [_shard(99, 100)]},
        {"0": [_shard(99, 100, 0)]},
        {"0": [_shard(99, 100, 50)]},
        {"0": [_shard(99, 100, 100)]},
    ]
    indexer = Indexer(
        "v1",
        category_blocklist,
        title_blocklist,
        file_manager,
        es_adapter,
        follower_sync_poll_interval=15,
        follower_discovery_period=30,
    )

    indexer._wait_for_followers("enwiki-1")

    assert es_adapter.get_shard_stats.call_count == 4


@freezegun.freeze_time(FROZEN_TIME)
def test_index_from_export_builds_under_temp_name_and_clones(
    indexer, file_manager, es_adapter, mocker
):
    """Test that documents go into the temp build index, which is force merged and
    cloned under the real name, and that followers are checked before the alias
    points at the clone.
    """
    build_index = f"temp-enwiki-20220101-v1-{EPOCH_FROZEN_TIME}"
    index_name = f"enwiki-20220101-v1-{EPOCH_FROZEN_TIME}"
    file_manager.get_latest_gcs.return_value = SNAPSHOT
    bulk_indices = []

    def capture_bulk(operations):
        """Record target indices at call time; the queue is cleared afterwards."""
        bulk_indices.extend(op["index"]["_index"] for op in operations if "index" in op)
        return {"acknowledged": True, "errors": False, "items": [{"id": 1000}]}

    es_adapter.bulk.side_effect = capture_bulk
    es_adapter.index_exists.return_value = False
    es_adapter.create_index.return_value = True
    es_adapter.alias_exists.return_value = False

    calls = mocker.Mock()
    for name in [
        "forcemerge",
        "block_writes",
        "clone_index",
        "get_shard_stats",
        "update_aliases",
        "delete_index",
    ]:
        calls.attach_mock(getattr(es_adapter, name), name)

    inputs = [
        json.dumps({"index": {"_type": "doc", "_id": "1000"}}),
        json.dumps({"title": "Paris", "page_id": 1000, "category": ["cities"]}),
    ]
    file_manager.stream_from_gcs.return_value = (input for input in inputs)

    indexer.index_from_export(1, "enwiki-{version}")

    assert [call[0] for call in calls.mock_calls] == [
        "forcemerge",
        "block_writes",
        "clone_index",
        "get_shard_stats",
        "update_aliases",
        "delete_index",
    ]
    assert es_adapter.create_index.call_args.kwargs["index"] == build_index
    assert bulk_indices == [build_index]
    assert es_adapter.forcemerge.call_args.kwargs["index"] == build_index
    # The clone would otherwise inherit the build's write block.
    es_adapter.clone_index.assert_called_once_with(
        source=build_index, target=index_name, settings={"index.blocks.write": None}
    )
    es_adapter.get_shard_stats.assert_called_with(index=index_name)
    es_adapter.update_aliases.assert_called_once_with(
        actions=[{"add": {"index": index_name, "alias": "enwiki-v1"}}]
    )
    es_adapter.delete_index.assert_called_once_with(index=build_index, ignore_missing=True)


def test_wait_for_followers_logs_each_follower_once_when_discovered(
    file_manager, es_adapter, category_blocklist, title_blocklist, clock, caplog
):
    """Test that each follower is logged once, on first sighting, with the seconds
    since the clone so that auto-follow pickup time can be measured.
    """
    es_adapter.get_shard_stats.side_effect = [
        {"0": [_shard(99, 100)]},
        {"0": [_shard(99, 100, 0)]},
        {"0": [_shard(99, 100, 100)]},
    ]
    indexer = Indexer(
        "v1",
        category_blocklist,
        title_blocklist,
        file_manager,
        es_adapter,
        follower_sync_poll_interval=15,
        follower_discovery_period=30,
    )

    with caplog.at_level(logging.INFO):
        indexer._wait_for_followers("enwiki-1", cloned_at=-10)

    discovered = [
        (r.follower, r.seconds_since_clone, r.index)
        for r in caplog.records
        if r.message == "Discovered follower"
    ]
    assert discovered == [("follower-0", 10.0, "enwiki-1"), ("follower-1", 25.0, "enwiki-1")]
