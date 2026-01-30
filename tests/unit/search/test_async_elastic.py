"""Unit tests for async elastic search adapter module"""

from unittest.mock import AsyncMock, MagicMock
import pytest
from merino.search.async_elastic import AsyncElasticSearchAdapter


pytestmark = pytest.mark.asyncio


@pytest.fixture
def adapter() -> AsyncElasticSearchAdapter:
    """Return an AsyncElasticSearchAdapter configured with dummy connection settings."""
    return AsyncElasticSearchAdapter(url="https://example:9200", api_key="abc123")


def _mock_async_client() -> MagicMock:
    """Return a mocked AsyncElasticsearch client with async methods and nested indices client.

    Provides:
      - client.search (async)
      - client.delete_by_query (async)
      - client.close (async)
      - client.indices.create/refresh/delete (async)
    """
    client = MagicMock(name="AsyncElasticsearchClient")
    client.search = AsyncMock(name="search")
    client.delete_by_query = AsyncMock(name="delete_by_query")
    client.close = AsyncMock(name="close")

    client.indices = MagicMock(name="IndicesClient")
    client.indices.create = AsyncMock(name="indices.create")
    client.indices.refresh = AsyncMock(name="indices.refresh")
    client.indices.delete = AsyncMock(name="indices.delete")

    return client


async def test_get_client_is_lazy_and_cached(
    adapter: AsyncElasticSearchAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ensure get_client lazily creates the AsyncElasticsearch client and returns
    the same cached instance on subsequent calls.
    """
    client = _mock_async_client()
    create_client = MagicMock(return_value=client)
    monkeypatch.setattr(adapter, "create_client", create_client)

    c1 = adapter.get_client()
    c2 = adapter.get_client()

    assert c1 is client
    assert c2 is client
    create_client.assert_called_once_with()


async def test_shutdown_closes_client_and_clears_cache(
    adapter: AsyncElasticSearchAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify shutdown closes the cached client and resets the adapter to an
    uninitialized state.
    """
    client = _mock_async_client()
    adapter._client = client  # simulate initialized client

    await adapter.shutdown()

    client.close.assert_awaited_once()
    assert adapter._client is None


async def test_shutdown_noop_when_no_client(adapter: AsyncElasticSearchAdapter) -> None:
    """Verify shutdown is a no-op when the adapter has not created a client yet."""
    assert adapter._client is None
    await adapter.shutdown()
    assert adapter._client is None


async def test_search_delegates_to_client_search(
    adapter: AsyncElasticSearchAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify search forwards parameters to AsyncElasticsearch.search and returns
    the raw response.
    """
    client = _mock_async_client()
    client.search.return_value = {"hits": {"hits": []}}
    monkeypatch.setattr(adapter, "get_client", MagicMock(return_value=client))

    res = await adapter.search(
        index="my-index",
        body={"query": {"match_all": {}}},
        suggest={"s": {"prefix": "a"}},
        timeout="1000ms",
        source_includes=["title"],
    )

    assert res == {"hits": {"hits": []}}
    client.search.assert_awaited_once_with(
        index="my-index",
        body={"query": {"match_all": {}}},
        suggest={"s": {"prefix": "a"}},
        timeout="1000ms",
        source_includes=["title"],
    )


async def test_create_index_sends_body_when_present(
    adapter: AsyncElasticSearchAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify create_index builds a body with mappings/settings/aliases and passes it
    to indices.create, returning the acknowledged flag.
    """
    client = _mock_async_client()
    client.indices.create.return_value = {"acknowledged": True}
    monkeypatch.setattr(adapter, "get_client", MagicMock(return_value=client))

    ok = await adapter.create_index(
        index="my-index",
        mappings={"properties": {"title": {"type": "keyword"}}},
        settings={"number_of_shards": 1},
        aliases={"my-alias": {}},
        wait_for_active_shards="all",
    )

    assert ok is True
    client.indices.create.assert_awaited_once_with(
        index="my-index",
        mappings={"properties": {"title": {"type": "keyword"}}},
        settings={"number_of_shards": 1},
        aliases={"my-alias": {}},
        wait_for_active_shards="all",
    )


async def test_create_index_omits_body_when_empty(
    adapter: AsyncElasticSearchAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify create_index does not pass a body when no mappings/settings/aliases are
    provided, and returns False when not acknowledged.
    """
    client = _mock_async_client()
    client.indices.create.return_value = {"acknowledged": False}
    monkeypatch.setattr(adapter, "get_client", MagicMock(return_value=client))

    ok = await adapter.create_index(index="my-index")

    assert ok is False
    client.indices.create.assert_awaited_once_with(
        index="my-index",
        mappings=None,
        settings=None,
        aliases=None,
        wait_for_active_shards="1",
    )


async def test_refresh_index_delegates_to_indices_refresh(
    adapter: AsyncElasticSearchAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify refresh_index delegates to indices.refresh with the provided index name."""
    client = _mock_async_client()
    monkeypatch.setattr(adapter, "get_client", MagicMock(return_value=client))

    await adapter.refresh_index(index="my-index")
    client.indices.refresh.assert_awaited_once_with(index="my-index")


async def test_delete_index_delegates_to_indices_delete(
    adapter: AsyncElasticSearchAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify delete_index calls indices.delete with ignore_unavailable and returns
    the acknowledged flag.
    """
    client = _mock_async_client()
    client.indices.delete.return_value = {"acknowledged": True}
    monkeypatch.setattr(adapter, "get_client", MagicMock(return_value=client))

    ok = await adapter.delete_index(index="my-index", ignore_unavailable=True)

    assert ok is True
    client.indices.delete.assert_awaited_once_with(
        index="my-index",
        ignore_unavailable=True,
    )


async def test_delete_by_query_delegates_to_client(
    adapter: AsyncElasticSearchAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify delete_by_query forwards all parameters to AsyncElasticsearch.delete_by_query
    and returns the raw response.
    """
    client = _mock_async_client()
    client.delete_by_query.return_value = {"deleted": 10, "failures": []}
    monkeypatch.setattr(adapter, "get_client", MagicMock(return_value=client))

    res = await adapter.delete_by_query(
        index="my-index",
        query={"term": {"language": "en"}},
        refresh=True,
        conflicts="proceed",
        wait_for_completion=False,
        timeout="30s",
    )

    assert res == {"deleted": 10, "failures": []}
    client.delete_by_query.assert_awaited_once_with(
        index="my-index",
        query={"term": {"language": "en"}},
        refresh=True,
        conflicts="proceed",
        wait_for_completion=False,
        timeout="30s",
    )
