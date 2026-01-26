"""Unit tests for the elastic search adapter module"""

from typing import Any
from unittest.mock import MagicMock
import pytest
from merino.search.elastic import ElasticSearchAdapter


@pytest.fixture
def adapter() -> ElasticSearchAdapter:
    """Return an ElasticSearchAdapter configured with dummy connection settings."""
    return ElasticSearchAdapter(url="https://example:9200", api_key="abc123")


def _mock_client() -> MagicMock:
    """Return a mocked Elasticsearch client"""
    client = MagicMock(name="ElasticsearchClient")
    client.indices = MagicMock(name="IndicesClient")
    return client


def test_get_client_is_lazy_and_cached(
    adapter: ElasticSearchAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that get_client lazily creates the Elasticsearch client and
    returns the same cached instance on subsequent calls.
    """
    client = _mock_client()
    create_client = MagicMock(return_value=client)
    monkeypatch.setattr(adapter, "create_client", create_client)

    c1 = adapter.get_client()
    c2 = adapter.get_client()

    assert c1 is client
    assert c2 is client
    create_client.assert_called_once_with()


def test_index_exists_calls_indices_exists(
    adapter: ElasticSearchAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify that index_exists calls indices.exists and returns its
    boolean result.
    """
    client = _mock_client()
    client.indices.exists.return_value = True
    monkeypatch.setattr(adapter, "get_client", MagicMock(return_value=client))

    assert adapter.index_exists(index="my-index") is True
    client.indices.exists.assert_called_once_with(index="my-index")


def test_create_index_returns_acknowledged_true(
    adapter: ElasticSearchAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify that create_index returns True when Elasticsearch acknowledges
    index creation.
    """
    client = _mock_client()
    client.indices.create.return_value = {"acknowledged": True}
    monkeypatch.setattr(adapter, "get_client", MagicMock(return_value=client))

    ok = adapter.create_index(
        index="my-index",
        mappings={"properties": {"title": {"type": "keyword"}}},
        settings={"number_of_shards": 1},
        aliases={"my-alias": {}},
        wait_for_active_shards="all",
    )

    assert ok is True
    client.indices.create.assert_called_once_with(
        index="my-index",
        mappings={"properties": {"title": {"type": "keyword"}}},
        settings={"number_of_shards": 1},
        aliases={"my-alias": {}},
        wait_for_active_shards="all",
    )


def test_create_index_returns_acknowledged_false_when_missing(
    adapter: ElasticSearchAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify that create_index returns False when the Elasticsearch response
    does not include an acknowledgement.
    """
    client = _mock_client()
    client.indices.create.return_value = {"acknowledged": False}
    monkeypatch.setattr(adapter, "get_client", MagicMock(return_value=client))

    ok = adapter.create_index(index="my-index")
    assert ok is False

    client.indices.create.assert_called_once_with(
        index="my-index",
        mappings=None,
        settings=None,
        aliases=None,
        wait_for_active_shards="1",
    )


def test_refresh_index_calls_indices_refresh(
    adapter: ElasticSearchAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ensure that refresh_index calls indices.refresh with the
    provided index name.
    """
    client = _mock_client()
    monkeypatch.setattr(adapter, "get_client", MagicMock(return_value=client))

    adapter.refresh_index(index="my-index")
    client.indices.refresh.assert_called_once_with(index="my-index")


def test_bulk_success_returns_response(
    adapter: ElasticSearchAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify that bulk returns the raw Elasticsearch response when there are
    no per-item errors.
    """
    client = _mock_client()
    resp = {"errors": False, "items": [{"index": {"status": 201}}]}
    client.bulk.return_value = resp
    monkeypatch.setattr(adapter, "get_client", MagicMock(return_value=client))

    ops: list[dict[str, Any]] = [{"index": {"_index": "my-index", "_id": "1"}}, {"title": "hello"}]
    res = adapter.bulk(operations=ops, raise_on_error=True)

    assert res is resp
    client.bulk.assert_called_once_with(operations=ops)


def test_bulk_errors_raises_with_first_error(
    adapter: ElasticSearchAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify that bulk raises a RuntimeError when raise_on_error is True and
    the response contains per-item failures, including details of the
    first failing item.
    """
    client = _mock_client()
    client.bulk.return_value = {
        "errors": True,
        "items": [
            {"index": {"status": 201}},
            {
                "index": {
                    "status": 400,
                    "_index": "my-index",
                    "_id": "2",
                    "error": {"type": "mapper_parsing_exception", "reason": "bad"},
                }
            },
        ],
    }
    monkeypatch.setattr(adapter, "get_client", MagicMock(return_value=client))

    with pytest.raises(RuntimeError) as exc:
        adapter.bulk(
            operations=[{"index": {"_index": "my-index", "_id": "2"}}, {"title": 123}],
            raise_on_error=True,
        )

    msg = str(exc.value)
    assert "Bulk failed. First error:" in msg
    assert "'action': 'index'" in msg
    assert "'status': 400" in msg
    assert "'index': 'my-index'" in msg
    assert "'id': '2'" in msg


def test_bulk_errors_does_not_raise_when_raise_on_error_false(
    adapter: ElasticSearchAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify that bulk returns the raw response and does not raise when
    raise_on_error is False, even if per-item errors are present.
    """
    client = _mock_client()
    resp = {
        "errors": True,
        "items": [
            {
                "index": {
                    "status": 400,
                    "_index": "my-index",
                    "_id": "1",
                    "error": {"type": "x"},
                }
            }
        ],
    }
    client.bulk.return_value = resp
    monkeypatch.setattr(adapter, "get_client", MagicMock(return_value=client))

    res = adapter.bulk(
        operations=[{"index": {"_index": "my-index", "_id": "1"}}, {"t": "x"}],
        raise_on_error=False,
    )

    assert res is resp


def test_alias_exists_calls_exists_alias(
    adapter: ElasticSearchAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify that alias_exists calls indices.exists_alias and returns
    its boolean result.
    """
    client = _mock_client()
    client.indices.exists_alias.return_value = True
    monkeypatch.setattr(adapter, "get_client", MagicMock(return_value=client))

    assert adapter.alias_exists(alias="my-alias") is True
    client.indices.exists_alias.assert_called_once_with(name="my-alias")


def test_get_indices_for_alias_returns_keys(
    adapter: ElasticSearchAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify that get_indices_for_alias returns a list of index names associated
    with the given alias.
    """
    client = _mock_client()
    client.indices.get_alias.return_value = {
        "index-a": {"aliases": {"my-alias": {}}},
        "index-b": {"aliases": {"my-alias": {}}},
    }
    monkeypatch.setattr(adapter, "get_client", MagicMock(return_value=client))

    indices = adapter.get_indices_for_alias(alias="my-alias")
    assert indices == ["index-a", "index-b"]
    client.indices.get_alias.assert_called_once_with(name="my-alias")


def test_update_aliases_calls_indices_update_aliases(
    adapter: ElasticSearchAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify that update_aliases calls indices.update_aliases with
    the provided actions.
    """
    client = _mock_client()
    monkeypatch.setattr(adapter, "get_client", MagicMock(return_value=client))

    actions: list[dict[str, Any]] = [
        {"add": {"index": "index-new", "alias": "my-alias"}},
        {"remove": {"index": "index-old", "alias": "my-alias"}},
    ]

    adapter.update_aliases(actions=actions)
    client.indices.update_aliases.assert_called_once_with(actions=actions)
