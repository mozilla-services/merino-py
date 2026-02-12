"""Async Elasticsearch service utilities."""

from typing import Any, Optional, cast

from elasticsearch import AsyncElasticsearch


class AsyncElasticSearchAdapter:
    """Wrapper around AsyncElasticsearch.

    - Lazily creates and caches an AsyncElasticsearch client instance.
    - Exposes async helpers for operations (search, close).
    """

    def __init__(
        self,
        *,
        url: str,
        api_key: str,
    ) -> None:
        self._url = url
        self._api_key = api_key
        self._client: Optional[AsyncElasticsearch] = None

    def create_client(self) -> AsyncElasticsearch:
        """Create an AsyncElasticsearch client."""
        self._client = AsyncElasticsearch(self._url, api_key=self._api_key)
        return self._client

    def get_client(self) -> AsyncElasticsearch:
        """Return the cached AsyncElasticsearch client, creating it if needed."""
        if self._client is None:
            self._client = self.create_client()
        return self._client

    async def shutdown(self) -> None:
        """Close the async client connection."""
        if self._client is not None:
            await self._client.close()
            self._client = None

    async def search(
        self,
        *,
        index: str,
        body: Optional[dict[str, Any]] = None,
        suggest: Optional[dict[str, Any]] = None,
        timeout: Optional[str] = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Run an async search request."""
        client = self.get_client()

        return cast(
            dict[str, Any],
            await client.search(
                index=index, body=body, suggest=suggest, timeout=timeout, **kwargs
            ),
        )

    async def create_index(
        self,
        *,
        index: str,
        mappings: Optional[dict[str, Any]] = None,
        settings: Optional[dict[str, Any]] = None,
        aliases: Optional[dict[str, Any]] = None,
        wait_for_active_shards: Optional[str | int] = "1",
    ) -> bool:
        """Create an index.

        Args:
            index: Index name.
            mappings: Optional mappings body.
            settings: Optional settings body.
            aliases: Optional aliases body.
            wait_for_active_shards: Passed through to ES to control shard
                availability before returning (e.g., "1", "all", or an int).

        Returns:
            True if Elasticsearch acknowledged index creation, otherwise False.
        """
        client = self.get_client()

        res = await client.indices.create(
            index=index,
            mappings=mappings,
            settings=settings,
            aliases=aliases,
            wait_for_active_shards=wait_for_active_shards,
        )

        return bool(res.get("acknowledged", False))

    async def refresh_index(self, *, index: str) -> None:
        """Refresh an index to make recent operations visible to search."""
        client = self.get_client()

        await client.indices.refresh(
            index=index,
        )

    async def delete_index(self, *, index: str, ignore_unavailable: bool = True) -> bool:
        """Delete an index.

        Args:
            index: Name of the index to delete.
            ignore_unavailable: If True, do not raise when the index does not exist.

        Returns:
            True if the delete request was acknowledged by Elasticsearch.
            False if the index did not exist and `ignore_unavailable` is True.
        """
        client = self.get_client()

        res = await client.indices.delete(
            index=index,
            ignore_unavailable=ignore_unavailable,
        )

        return bool(res.get("acknowledged", False))

    async def delete_by_query(
        self,
        *,
        index: str,
        query: dict[str, Any],
        refresh: bool | None = None,
        conflicts: str | None = None,
        wait_for_completion: bool | None = None,
        timeout: Optional[str] = None,
    ) -> dict[str, Any]:
        """Delete documents matching a query.

        Args:
            index: Name of the index (or index pattern) to delete documents from.
            query: Elasticsearch query DSL describing documents to delete.
            refresh: If True, refresh affected shards to make the deletion visible
                to search.
            conflicts: What to do when version conflicts occur. Valid values are
                'abort' or 'proceed'.
            wait_for_completion: If False, the request is executed asynchronously
                and returns a task ID instead of waiting for completion.

        Returns:
            The raw delete-by-query response from Elasticsearch
        """
        client = self.get_client()

        result = await client.delete_by_query(
            index=index,
            query=query,
            refresh=refresh,
            conflicts=conflicts,
            wait_for_completion=wait_for_completion,
            timeout=timeout,
        )
        return cast(dict[str, Any], result)
