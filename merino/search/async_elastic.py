"""Async Elasticsearch service utilities."""

from typing import Any, Dict, Iterable, Mapping, Optional

from elasticsearch import AsyncElasticsearch


class AsyncElasticSearchAdapter:
    """
    Wrapper around AsyncElasticsearch.

    - Lazily creates and caches an AsyncElasticsearch client instance.
    - Exposes async helpers for operations (search, close).
    """

    def __init__(
        self, *, url: str, api_key: str, timeout_ms: Optional[int] = None
    ) -> None:
        self._url = url
        self._api_key = api_key
        self._timeout_ms = timeout_ms
        self._client: Optional[AsyncElasticsearch] = None

    def create_client(self) -> AsyncElasticsearch:
        """Create an AsyncElasticsearch client."""
        self._client = AsyncElasticsearch(self._url, api_key=self._api_key)
        return self._client

    def get_client(self) -> AsyncElasticsearch:
        """Return the cached AsyncElasticsearch client, creating it if needed."""
        if self._client is None:
            return self.create_client()
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
        body: Optional[Mapping[str, Any]] = None,
        suggest: Optional[Mapping[str, Any]] = None,
        timeout: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Run an async search request.

        Accepts `timeout` in the same form your callers expect (e.g. "1000ms").
        Extra kwargs are forwarded to AsyncElasticsearch.search.
        """
        client = self.get_client()
        # Prefer explicit timeout, fall back to configured value (string like "1000ms" if needed).
        if timeout is None and self._timeout_ms is not None:
            timeout = f"{self._timeout_ms}ms"

        return await client.search(
            index=index, body=body, suggest=suggest, timeout=timeout, **kwargs
        )

    async def indices_get_alias(self, *, name: str) -> Dict[str, Any]:
        """Return the raw alias metadata as returned by ES (awaitable wrapper)."""
        client = self.get_client()
        return await client.indices.get_alias(name=name)

    async def indices_exists_alias(self, *, name: str) -> bool:
        """Return whether an alias exists (awaitable wrapper)."""
        client = self.get_client()
        return await client.indices.exists_alias(name=name)

    async def indices_update_aliases(
        self, *, actions: Iterable[Mapping[str, Any]]
    ) -> Dict[str, Any]:
        """Apply alias update actions atomically (awaitable wrapper)."""
        client = self.get_client()
        return await client.indices.update_aliases(actions=actions)
