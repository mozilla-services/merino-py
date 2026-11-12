"""End-to-end tests for the wikipedia indexer against a CCR leader and follower.

The indexer only talks to the leader. A second cluster auto-follows it (see the
`ccr_clusters` fixture), standing in for the replicas Merino serves from.
"""

import datetime
import json
import logging
from collections.abc import Iterator
from unittest.mock import MagicMock

import pytest
from elasticsearch import Elasticsearch
from pytest_mock import MockerFixture

from merino.jobs.wikipedia_indexer.filemanager import Snapshot
from merino.jobs.wikipedia_indexer.indexer import Indexer
from merino.search.elastic import ElasticSearchAdapter
from tests.utils.polling import eventually

DOCS = 500
ALIAS = "enwiki-ccr-{version}"


def _export(docs: int) -> Iterator[str]:
    """Yield a wikipedia export as alternating operation and document lines."""
    for i in range(docs):
        yield json.dumps({"index": {"_id": str(i)}})
        yield json.dumps(
            {"title": f"Article {i}", "page_id": i, "incoming_links": 1, "popularity_score": 0.1}
        )


@pytest.fixture
def clients(ccr_clusters: tuple[str, str]) -> Iterator[tuple[Elasticsearch, Elasticsearch]]:
    """Return (leader, follower) clients, removing indices the test created."""
    leader_url, follower_url = ccr_clusters
    leader, follower = Elasticsearch(leader_url), Elasticsearch(follower_url)
    yield leader, follower
    for index in follower.indices.get(index="*wiki-*", expand_wildcards="open"):
        follower.ccr.pause_follow(index=index)
        follower.indices.close(index=index)
        follower.ccr.unfollow(index=index)
        follower.indices.delete(index=index)
    # Deleting by wildcard is disallowed (`action.destructive_requires_name`).
    for index in leader.indices.get(index="*wiki-*,temp-*", expand_wildcards="open"):
        leader.indices.delete(index=index)
    leader.close()
    follower.close()


def _indexer(leader: Elasticsearch) -> Indexer:
    """Return an indexer that builds a small export on `leader`."""
    file_manager = MagicMock(language="en")
    file_manager.get_latest_gcs.return_value = Snapshot(
        name="enwiki-20260101-cirrussearch-content",
        date=datetime.datetime(2026, 1, 1),
        prefix="enwiki-20260101-cirrussearch-content",
    )
    file_manager.stream_from_gcs.side_effect = lambda _: _export(DOCS)
    adapter = ElasticSearchAdapter(
        url=leader.transport.node_pool.get().base_url,
        api_key="unused",
        request_timeout=60,
        create_index_timeout=60,
    )
    return Indexer(
        "v1",
        set(),
        set(),
        file_manager,
        adapter,
        follower_sync_timeout=120,
        follower_sync_poll_interval=1,
        follower_discovery_period=10,
    )


def _lifecycle_policy(client: Elasticsearch, index: str) -> str | None:
    """Return the ILM policy name set on `index`."""
    res = client.indices.get_settings(index=index, name="index.lifecycle.name")
    policy = res[index]["settings"].get("index", {}).get("lifecycle", {}).get("name")
    return str(policy) if policy is not None else None


def test_followers_start_with_the_finished_index_before_the_alias_flips(
    clients: tuple[Elasticsearch, Elasticsearch], caplog: pytest.LogCaptureFixture
) -> None:
    """Verify followers never see the build, and hold the complete, force merged,
    searchable index by the time the alias, which replicates to them, flips.
    """
    leader, follower = clients
    indexer = _indexer(leader)

    with caplog.at_level(logging.INFO, logger="merino.jobs.wikipedia_indexer.indexer"):
        indexer.index_from_export(DOCS, ALIAS)

    [index] = leader.indices.get_alias(name="enwiki-ccr-v1")
    assert not leader.indices.exists(index=f"temp-{index}")
    # Single-node clusters get no replica, so the index is fully allocated (green).
    assert leader.cluster.health(index=index)["status"] == "green"

    # The indexer found the follower through its retention lease on the leader.
    [discovered] = [r.__dict__ for r in caplog.records if r.message == "Discovered follower"]
    assert f"/{index}/" in discovered["follower"]
    assert discovered["seconds_since_clone"] < 10

    # The follower bootstrapped from the finished clone, never from the build...
    assert list(follower.indices.get(index="*wiki-*,temp-*")) == [index]
    # ...so it carries the leader's single merged segment, and serves every document
    # despite the `refresh_interval: -1` it inherits and nothing ever refreshing it.
    [shard] = follower.indices.segments(index=index)["indices"][index]["shards"]["0"]
    assert len(shard["segments"]) == 1
    assert follower.count(index=index)["count"] == DOCS

    # The alias flip on the leader reaches the follower.
    eventually(lambda: follower.indices.exists_alias(name="enwiki-ccr-v1"))
    assert list(follower.indices.get_alias(name="enwiki-ccr-v1")) == [index]

    # The switch to the never-delete policy replicates while the follow is running.
    eventually(lambda: _lifecycle_policy(follower, index) == "enwiki_policy")


def test_unpublished_index_keeps_the_expiring_policy_when_the_wait_fails(
    clients: tuple[Elasticsearch, Elasticsearch], mocker: MockerFixture
) -> None:
    """Verify a run failing after followers caught up, but before the never-delete
    policy is attached (e.g. a follower wait timeout), leaves the index in place on
    the backup policy, on the leader and followers alike, for ILM to expire.
    """
    leader, follower = clients
    indexer = _indexer(leader)
    mocker.patch.object(
        indexer, "_apply_active_lifecycle_policy", side_effect=RuntimeError("boom")
    )

    with pytest.raises(RuntimeError, match="boom"):
        indexer.index_from_export(DOCS, ALIAS)

    [index] = leader.indices.get(index="*wiki-*,temp-*")
    assert not index.startswith("temp-")
    assert _lifecycle_policy(leader, index) == "enwiki_backup_policy"
    assert list(follower.indices.get(index="*wiki-*")) == [index]
    assert _lifecycle_policy(follower, index) == "enwiki_backup_policy"


def test_unpublished_index_reverts_to_the_expiring_policy_when_the_flip_fails(
    clients: tuple[Elasticsearch, Elasticsearch], mocker: MockerFixture
) -> None:
    """Verify a run failing after the never-delete policy is attached, but before the
    alias flips, switches the index back to the backup policy, and that the revert
    reaches the followers, since the index is left in place and still followed.
    """
    leader, follower = clients
    indexer = _indexer(leader)
    mocker.patch.object(indexer.elasticsearch, "update_aliases", side_effect=RuntimeError("boom"))

    with pytest.raises(RuntimeError, match="boom"):
        indexer.index_from_export(DOCS, ALIAS)

    [index] = leader.indices.get(index="*wiki-*,temp-*")
    assert _lifecycle_policy(leader, index) == "enwiki_backup_policy"
    eventually(lambda: _lifecycle_policy(follower, index) == "enwiki_backup_policy")
