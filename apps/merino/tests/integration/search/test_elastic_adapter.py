"""Integration tests for ElasticSearchAdapter against a real Elasticsearch container.

These cover the response shapes and API semantics that the wikipedia indexer relies on
and that mocked clients cannot verify.
"""

from collections.abc import Iterator

import pytest
from elasticsearch import AuthorizationException

from merino.search.elastic import ElasticSearchAdapter

SOURCE = "adapter-test-source"
CLONE = "adapter-test-clone"


@pytest.fixture
def adapter(es_url: str) -> Iterator[ElasticSearchAdapter]:
    """Return an adapter for the container, with a populated single-shard index."""
    adapter = ElasticSearchAdapter(
        url=es_url, api_key="unused", request_timeout=30, create_index_timeout=60
    )
    adapter.create_index(index=SOURCE, settings={"number_of_shards": 1, "number_of_replicas": 0})
    adapter.bulk(
        operations=[
            op
            for i in range(3)
            for op in ({"index": {"_index": SOURCE, "_id": str(i)}}, {"title": f"doc {i}"})
        ]
    )
    adapter.refresh_index(index=SOURCE)
    yield adapter
    for index in (CLONE, SOURCE):
        adapter.delete_index(index=index, ignore_missing=True)


def test_get_shard_stats_exposes_checkpoints_and_retention_leases(
    adapter: ElasticSearchAdapter,
) -> None:
    """Verify the fields the indexer reads to track CCR followers are present."""
    shards = adapter.get_shard_stats(index=SOURCE)

    assert list(shards) == ["0"]
    [primary] = [copy for copy in shards["0"] if copy["routing"]["primary"]]
    assert primary["seq_no"]["global_checkpoint"] == 2
    leases = primary["retention_leases"]["leases"]
    assert leases, "a primary always holds at least its own peer recovery lease"
    assert {"id", "retaining_seq_no", "source"} <= leases[0].keys()


def test_clone_index_clears_the_inherited_write_block(adapter: ElasticSearchAdapter) -> None:
    """Verify a blocked index can be cloned, and the clone left writable."""
    adapter.block_writes(index=SOURCE)
    adapter.clone_index(source=SOURCE, target=CLONE, settings={"index.blocks.write": None})

    client = adapter.get_client()
    assert client.count(index=CLONE)["count"] == 3
    # `null` clears the block copied from the source (the setting reads back as null).
    client.index(index=CLONE, id="new", document={"title": "new"})
    with pytest.raises(AuthorizationException, match="index write"):
        client.index(index=SOURCE, id="new", document={"title": "new"})
