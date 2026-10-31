"""End-to-end tests for the wikipedia indexer against a CCR leader and follower.

The indexer only talks to the leader. A second cluster auto-follows it (see the
`ccr_clusters` fixture), standing in for the replicas Merino serves from.
"""

import datetime
import json
import logging
import time
from collections.abc import Callable, Iterator
from typing import Any
from unittest.mock import MagicMock

import pytest
from elasticsearch import Elasticsearch

from merino.jobs.wikipedia_indexer.filemanager import Snapshot
from merino.jobs.wikipedia_indexer.indexer import Indexer
from merino.search.elastic import ElasticSearchAdapter

DOCS = 500
ALIAS = "enwiki-ccr-{version}"


def _export(docs: int) -> Iterator[str]:
    """Yield a wikipedia export as alternating operation and document lines."""
    for i in range(docs):
        yield json.dumps({"index": {"_id": str(i)}})
        yield json.dumps(
            {"title": f"Article {i}", "page_id": i, "incoming_links": 1, "popularity_score": 0.1}
        )


def _eventually(check: Callable[[], Any], timeout: float = 30) -> Any:
    """Return the first truthy result of check, polling until timeout."""
    deadline = time.monotonic() + timeout
    while not (result := check()):
        if time.monotonic() >= deadline:
            raise AssertionError(f"Condition not met within {timeout}s")
        time.sleep(0.5)
    return result


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


def test_followers_start_with_the_finished_index_before_the_alias_flips(
    clients: tuple[Elasticsearch, Elasticsearch], caplog: pytest.LogCaptureFixture
) -> None:
    """Verify followers never see the build, and hold the complete, force merged,
    searchable index by the time the alias, which replicates to them, flips.
    """
    leader, follower = clients
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
    indexer = Indexer(
        "v1",
        set(),
        set(),
        file_manager,
        adapter,
        follower_sync_timeout=120,
        follower_sync_poll_interval=1,
        follower_discovery_period=10,
    )

    with caplog.at_level(logging.INFO, logger="merino.jobs.wikipedia_indexer.indexer"):
        indexer.index_from_export(DOCS, ALIAS)

    [index] = leader.indices.get_alias(name="enwiki-ccr-v1")
    assert not leader.indices.exists(index=f"temp-{index}")

    # The indexer found the follower through its retention lease on the leader.
    [discovered] = [r for r in caplog.records if r.message == "Discovered follower"]
    assert f"/{index}/" in discovered.follower
    assert discovered.seconds_since_clone < 10

    # The follower bootstrapped from the finished clone, never from the build...
    assert list(follower.indices.get(index="*wiki-*,temp-*")) == [index]
    # ...so it carries the leader's single merged segment, and serves every document
    # despite the `refresh_interval: -1` it inherits and nothing ever refreshing it.
    [shard] = follower.indices.segments(index=index)["indices"][index]["shards"]["0"]
    assert len(shard["segments"]) == 1
    assert follower.count(index=index)["count"] == DOCS

    # The alias flip on the leader reaches the follower.
    _eventually(lambda: follower.indices.exists_alias(name="enwiki-ccr-v1"))
    assert list(follower.indices.get_alias(name="enwiki-ccr-v1")) == [index]
