"""Elasticsearch service utilities."""

from typing import Any, Literal, Mapping, Sequence, cast

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
        request_timeout: float,
        create_index_timeout: float,
    ) -> None:
        self._url = url
        self._api_key = api_key
        self._request_timeout = request_timeout
        self._create_index_timeout = create_index_timeout
        self._client: Elasticsearch | None = None

    def create_client(self) -> Elasticsearch:
        """Create a new Elasticsearch client instance."""
        return Elasticsearch(
            self._url,
            api_key=self._api_key,
            request_timeout=self._request_timeout,
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
        request_timeout: float | None = None,
    ) -> bool:
        """Create an index and return whether the operation was acknowledged.

        Note: This does not check for existence. Call `index_exists()` if needed.
        """
        res = (
            self.get_client()
            .options(request_timeout=request_timeout or self._create_index_timeout)
            .indices.create(
                index=index,
                mappings=mappings,
                settings=settings,
                aliases=aliases,
                wait_for_active_shards=wait_for_active_shards,
            )
        )
        return bool(res.get("acknowledged", False))

    def refresh_index(self, *, index: str) -> None:
        """Refresh an index to make recent operations visible to search."""
        self.get_client().indices.refresh(index=index)

    def delete_index(self, *, index: str, ignore_missing: bool = False) -> None:
        """Delete an index.

        Set `ignore_missing` when the index may never have been created, so that a
        missing index is not treated as a failure.
        """
        self.get_client().options(ignore_status=[404] if ignore_missing else []).indices.delete(
            index=index
        )

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

    def forcemerge(
        self,
        *,
        index: str,
        max_num_segments: int = 1,
        request_timeout: float | None = None,
        wait_for_completion: bool | None = None,
    ) -> None:
        """Force merge index segments to increase performance on read-only indices.
        See https://www.elastic.co/docs/deploy-manage/production-guidance/optimize-performance/search-speed#_force_merge_read_only_indices
        """
        self.get_client().options(request_timeout=request_timeout).indices.forcemerge(
            index=index,
            max_num_segments=max_num_segments,
            wait_for_completion=wait_for_completion,
        )

    def block_writes(self, *, index: str) -> None:
        """Add a write block to an index, e.g. before cloning it."""
        self.get_client().indices.add_block(index=index, block="write")

    def wait_for_health(
        self, *, index: str, status: Literal["green", "yellow"], timeout: float
    ) -> None:
        """Block until `index` reaches `status` health or better.

        Raises:
            TimeoutError: If `index` has not reached `status` within `timeout` seconds.
        """
        res = cast(
            dict[str, Any],
            self.get_client()
            .options(
                # The wait happens server side, so the request must outlast it.
                request_timeout=timeout + self._request_timeout,
                # A wait that times out is answered with a 408 and the current health.
                ignore_status=408,
            )
            .cluster.health(
                index=index, wait_for_status=status, timeout=f"{int(timeout * 1000)}ms"
            ),
        )
        if res["timed_out"]:
            raise TimeoutError(
                f"{index} did not reach {status} health within {timeout}s "
                f"(status: {res['status']})"
            )

    def clone_index(
        self,
        *,
        source: str,
        target: str,
        settings: dict[str, Any] | None = None,
        wait_for_active_shards: str | int = "1",
        active_shards_timeout: str | None = None,
        request_timeout: float | None = None,
    ) -> None:
        """Clone `source` into a new index `target`.

        The source must carry a write block. `settings` override those copied from the
        source onto the target. `active_shards_timeout` (e.g. `"30s"`) bounds the
        server-side wait for `wait_for_active_shards`, using Elasticsearch's default of
        30s when unset. `request_timeout` bounds the whole request on the client side.

        Raises:
            RuntimeError: If the master node did not acknowledge the clone in time
                (`acknowledged`), or the target's shards did not start before the
                `wait_for_active_shards` timeout (`shards_acknowledged`). In either case
                the target may still be created later.
        """
        res = cast(
            dict[str, Any],
            self.get_client()
            .options(request_timeout=request_timeout or self._create_index_timeout)
            .indices.clone(
                index=source,
                target=target,
                settings=settings,
                wait_for_active_shards=wait_for_active_shards,
                timeout=active_shards_timeout,
            ),
        )
        if not res.get("acknowledged"):
            raise RuntimeError(f"Clone of {source} to {target} was not acknowledged")
        if not res.get("shards_acknowledged"):
            raise RuntimeError(
                f"Clone of {source} to {target} did not start {wait_for_active_shards} "
                "active shard copies before timing out"
            )

    def get_shard_stats(self, *, index: str) -> dict[str, list[dict[str, Any]]]:
        """Return shard-level stats for `index`, keyed by shard number.

        Each shard number maps to a list with one entry per shard copy (primary and
        replicas), including its `routing`, `seq_no` and `retention_leases`. Only
        started copies are listed, so a shard with none is absent, and an index with
        none at all yields an empty dict.
        """
        res = cast(
            dict[str, Any],
            self.get_client().indices.stats(index=index, level="shards"),
        )
        if index not in res["indices"]:
            return {}
        return cast(dict[str, list[dict[str, Any]]], res["indices"][index]["shards"])

    def get_number_of_shards(self, *, index: str) -> int:
        """Return the number of primary shards configured for `index`."""
        res = cast(
            dict[str, Any],
            self.get_client().indices.get_settings(index=index, name="index.number_of_shards"),
        )
        return int(res[index]["settings"]["index"]["number_of_shards"])

    def get_index_lifecycle_policies(self, *, index: str) -> dict[str, str | None]:
        """Return the ILM policy attached to each index matching `index`.

        `index` may be a concrete name or a wildcard pattern. Indices that have
        no ILM policy attached map to `None`.
        """
        res = cast(
            dict[str, Any],
            self.get_client().indices.get_settings(index=index, ignore_unavailable=True),
        )
        policies: dict[str, str | None] = {}
        for name, body in res.items():
            index_settings = (body.get("settings") or {}).get("index") or {}
            policies[name] = (index_settings.get("lifecycle") or {}).get("name")
        return policies

    def set_index_lifecycle_policy(self, *, index: str, policy: str) -> None:
        """Attach an ILM policy to an index."""
        self.get_client().indices.put_settings(
            index=index,
            settings={"index.lifecycle.name": policy},
        )

    def update_aliases(self, *, actions: list[dict[str, Any]]) -> None:
        """Apply alias update actions atomically."""
        self.get_client().indices.update_aliases(
            actions=actions,
        )
