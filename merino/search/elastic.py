"""Elasticsearch service utilities."""

from typing import Any, Mapping, Sequence, cast

from elasticsearch import Elasticsearch


class ElasticSearchAdapter:
    """A wrapper around the Elasticsearch Python client.

    Instances are configured with a URL and API key and lazily create the
    underlying Elasticsearch client on first use..
    """

    def __init__(
        self,
        *,
        url: str,
        api_key: str,
    ) -> None:
        self._url = url
        self._api_key = api_key
        self._client: Elasticsearch | None = None

    def create_client(self) -> Elasticsearch:
        """Create a new Elasticsearch client instance."""
        return Elasticsearch(
            self._url,
            api_key=self._api_key,
        )

    def get_client(self) -> Elasticsearch:
        """Return the underlying Elasticsearch client, creating it if needed.

        The client is created lazily and cached on the service instance.
        """
        if self._client is None:
            self._client = self.create_client()
        return self._client

    def index_exists(self, *, index: str) -> bool:
        """Return True if the index exists."""
        return bool(self.get_client().indices.exists(index=index))

    def create_index(
        self,
        *,
        index: str,
        mappings: dict[str, Any] | None = None,
        settings: dict[str, Any] | None = None,
        aliases: dict[str, Any] | None = None,
        wait_for_active_shards: str | int = "1",
    ) -> bool:
        """Create an index and return whether the operation was acknowledged.

        Note: This does not check for existence. Call `index_exists()` if needed.
        """
        res = self.get_client().indices.create(
            index=index,
            mappings=mappings,
            settings=settings,
            aliases=aliases,
            wait_for_active_shards=wait_for_active_shards,
        )
        return bool(res.get("acknowledged", False))

    def refresh_index(self, *, index: str) -> None:
        """Refresh an index to make recent operations visible to search."""
        self.get_client().indices.refresh(index=index)

    def bulk(
        self,
        *,
        operations: Sequence[Mapping[str, Any]],
        raise_on_error: bool = True,
    ) -> dict[str, Any]:
        """Execute a bulk operation against Elasticsearch.

        Args:
            operations: Iterable of bulk operations, typically action/document
                pairs as expected by the Elasticsearch bulk API.
            raise_on_error: If True, raise an exception when Elasticsearch reports
                one or more failed bulk items. If False, return the raw response
                and allow the caller to inspect partial failures.

        Returns:
            The raw bulk API response from Elasticsearch.

        Raises:
            RuntimeError: If raise_on_error=True and the bulk response contains
                one or more failed items.
        """
        res = cast(
            dict[str, Any],
            self.get_client().bulk(
                operations=operations,
            ),
        )

        if raise_on_error and res.get("errors"):
            items = res.get("items", []) or []
            first_err: dict[str, Any] | None = None

            for it in items:
                action = next(
                    (k for k in ("index", "create", "update", "delete") if k in it),
                    None,
                )
                if not action:
                    continue
                meta = it[action] or {}
                if meta.get("error"):
                    first_err = {
                        "action": action,
                        "status": meta.get("status"),
                        "index": meta.get("_index"),
                        "id": meta.get("_id"),
                        "error": meta.get("error"),
                    }
                    break

            raise RuntimeError(f"Bulk failed. First error: {first_err}")

        return res

    def alias_exists(self, *, alias: str) -> bool:
        """Return True if the alias exists."""
        return bool(self.get_client().indices.exists_alias(name=alias))

    def get_indices_for_alias(self, *, alias: str) -> list[str]:
        """Return a list of index names currently associated with an alias."""
        indices = cast(dict[str, Any], self.get_client().indices.get_alias(name=alias))
        return list(indices.keys())

    def update_aliases(self, *, actions: list[dict[str, Any]]) -> None:
        """Apply alias update actions atomically."""
        self.get_client().indices.update_aliases(
            actions=actions,
        )
