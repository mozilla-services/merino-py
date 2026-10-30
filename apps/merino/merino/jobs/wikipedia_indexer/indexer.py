"""Builds the elasticsearch index from the export file"""

import json
import logging
import time
from itertools import islice
from typing import Any, Dict, Mapping

from merino.jobs.wikipedia_indexer.filemanager import FileManager
from merino.jobs.wikipedia_indexer.settings import get_settings_for_version
from merino.jobs.wikipedia_indexer.settings.v1 import (
    get_suggest_mapping,
    get_suggest_settings,
)
from merino.jobs.wikipedia_indexer.suggestion import Builder
from merino.jobs.wikipedia_indexer.utils import ProgressReporter
from merino.search.elastic import ElasticSearchAdapter

logger = logging.getLogger(__name__)

# Page type the export uses for a redirect, e.g. "Paris, France" pointing at "Paris".
REDIRECT_PAGE_TYPE = "redirect"

# ILM policies are provisioned per language by terraform in webservices-infra
# (merino/tf/modules/elasticsearch). The active policy never deletes, so the index
# serving the alias survives however long it takes to build a replacement; the
# backup policy expires superseded indices after 7 days.
ACTIVE_ILM_POLICY = "{language}wiki_policy"
BACKUP_ILM_POLICY = "{language}wiki_backup_policy"

# Matches every index this job has built for a language and index version,
# e.g. `enwiki-20240101-v1-1700000000`.
INDEX_PATTERN = "{language}wiki-*-{version}-*"

# Source of the retention lease a cross-cluster replication follower holds on each
# leader shard. Followers renew it with their global checkpoint + 1 as they replicate.
CCR_RETENTION_LEASE_SOURCE = "ccr"

# Prefix for the index a run builds into before cloning it under its real name.
# CCR auto-follow patterns exclude `temp-*`, so followers never see a partial build.
BUILD_INDEX_PREFIX = "temp-"


class Indexer:
    """Index documents from wikimedia search exports into Elasticsearch"""

    QUEUE_MAX_LENGTH = 5000

    queue: list[Mapping[str, Any]]
    suggestion_builder: Builder
    index_version: str
    file_manager: FileManager
    elasticsearch: ElasticSearchAdapter
    category_blocklist: set[str]
    title_blocklist: set[str]

    def __init__(
        self,
        index_version: str,
        category_blocklist: set[str],
        title_blocklist: set[str],
        file_manager: FileManager,
        elasticsearch: ElasticSearchAdapter,
        follower_sync_timeout: float = 3600,
        follower_sync_poll_interval: float = 15,
        follower_discovery_period: float = 60,
    ):
        self.queue = []
        self.follower_sync_timeout = follower_sync_timeout
        self.follower_sync_poll_interval = follower_sync_poll_interval
        self.follower_discovery_period = follower_discovery_period
        self.index_version = index_version
        self.file_manager = file_manager
        self.elasticsearch = elasticsearch
        self.suggestion_builder = Builder(index_version)
        self.category_blocklist = category_blocklist
        self.title_blocklist = {entry.lower() for entry in title_blocklist}

    def index_from_export(self, total_docs: int, elasticsearch_alias: str):
        """Primary indexer method.
        Reads the export file directly from GCS, indexes and swaps index aliases
        """
        language = self.file_manager.language
        logger.info(f"Ensuring latest {language} dump is on GCS")
        latest = self.file_manager.get_latest_gcs()
        if latest is None:
            raise RuntimeError(f"No exports available on GCS for {language}")

        # parse the index name out of the latest file name
        index_name = self._get_index_name(latest.name)
        # The index is built under a temporary name that CCR auto-follow patterns
        # exclude, then cloned to `index_name` once complete. Followers bootstrap by
        # copying the leader's segment files, so they start out with the finished,
        # force merged and searchable index rather than replaying the build.
        build_index = f"{BUILD_INDEX_PREFIX}{index_name}"
        logger.info("Ensuring index exists", extra={"index": build_index})

        if self._create_index(build_index):
            try:
                logger.info("Start indexing", extra={"index": build_index})
                reporter = ProgressReporter(
                    logger, "Indexing", latest.name, build_index, total_docs
                )
                indexed = 0
                blocked = 0
                gcs_stream = self.file_manager.stream_from_gcs(latest)
                # The following will chunk `gcs_stream` into a sequence of pairs of
                # (`operator`, `document`), where the first element as the operator
                # (i.e. `index`), the second element as the document data for the
                # operator
                while pair := tuple(islice(gcs_stream, 2)):
                    operator, document = pair
                    op = json.loads(operator)
                    doc = json.loads(document)

                    if self._should_filter(doc):
                        blocked += 1
                    else:
                        self._enqueue(build_index, (op, doc))
                        indexed += self._index_docs(False)

                    # report percent completed
                    reporter.report(indexed, blocked)

                # Flush queue after enumerating the export to clear the queue
                self._index_docs(True)
                logger.info(
                    "Completed indexing",
                    extra={"latest_name": latest.name, "index": build_index},
                )

                # Refresh the new index
                self.elasticsearch.refresh_index(index=build_index)
                logger.info("Refreshed index", extra={"index": build_index})

                # Force merge to a single segment for optimal read performance.
                # This is a long-running operation on large indices; use a 2-hour timeout.
                self.elasticsearch.forcemerge(
                    index=build_index,
                    max_num_segments=1,
                    request_timeout=7200,
                    wait_for_completion=True,
                )
                logger.info("Force merged index", extra={"index": build_index})

                self._clone_build_index(build_index, index_name)
                cloned_at = time.monotonic()

                # Attach the never-delete policy before the swap so the index is never
                # eligible for deletion while it is the one serving the alias.
                self._apply_active_lifecycle_policy(index_name)

                # Alias changes replicate to CCR followers independently of the data,
                # so wait for followers to catch up before the alias goes live there.
                self._wait_for_followers(index_name, cloned_at)

                # Flip the alias pointer to the new index and remove the previous index
                alias = self._flip_alias_to_latest(index_name, elasticsearch_alias)
            except Exception:
                self._discard_index(index_name)
                raise
            else:
                logger.info(
                    "Flipped alias to latest index",
                    extra={"index": index_name, "alias": alias},
                )

                # Anything the alias no longer points at is now a backup, so hand it
                # over to the expiring policy.
                self._apply_backup_lifecycle_policies(alias)
            finally:
                self._discard_index(build_index)
        else:
            raise Exception("Could not create the index")

    def _clone_build_index(self, build_index: str, index_name: str) -> None:
        """Clone the finished `build_index` to `index_name`.

        Cloning requires a write block on the source. The clone would inherit it, so
        it is lifted on the target to leave `index_name` as a regular index.
        """
        self.elasticsearch.block_writes(index=build_index)
        self.elasticsearch.clone_index(
            source=build_index,
            target=index_name,
            settings={"index.blocks.write": None},
        )
        logger.info("Cloned index", extra={"source": build_index, "index": index_name})

    def _discard_index(self, index_name: str) -> None:
        """Delete an index this run built but never published."""
        try:
            self.elasticsearch.delete_index(index=index_name, ignore_missing=True)
            logger.info("Discarded unpublished index", extra={"index": index_name})
        except Exception:
            logger.exception("Failed to discard unpublished index", extra={"index": index_name})

    def _should_filter(self, doc: Dict[str, Any]) -> bool:
        """Return True if we want to filter out this document and not index it.
        Checks for redirects, matching categories, or title in the category and title blocklists.
        """
        categories: set[str] = set(doc.get("category", []))
        title: str = doc.get("title", "")
        should_filter_redirect: bool = doc.get("page_type") == REDIRECT_PAGE_TYPE
        should_filter_category: bool = not self.category_blocklist.isdisjoint(categories)
        should_filter_title: bool = title.lower() in self.title_blocklist if title != "" else True
        return should_filter_redirect or should_filter_category or should_filter_title

    def _enqueue(self, index_name: str, tpl: tuple[Mapping[str, Any], ...]):
        op, doc = self._parse_tuple(index_name, tpl)
        self.queue.append(op)
        self.queue.append(doc)

    def _index_docs(self, force: bool) -> int:
        qlen = len(self.queue)
        item_count = 0
        if qlen > 0 and (qlen >= self.QUEUE_MAX_LENGTH or force):
            try:
                res = self.elasticsearch.bulk(operations=self.queue)
                item_count = len(res.get("items", []))
            except RuntimeError as e:
                logger.error(f"Wiki bulk indexing failed: {e}")
                raise
            finally:
                self.queue.clear()
        return item_count

    def _parse_tuple(
        self, index_name: str, tpl: tuple[Mapping[str, Any], ...]
    ) -> tuple[dict[str, Any], ...]:
        op, doc = tpl
        if "index" not in op:
            raise Exception("invalid operation")
        # re use the wikipedia ID (this keeps the indexing
        # operation idempotent from our side)
        id = op["index"]["_id"]
        # TODO make this more generic
        op = {"index": {"_index": index_name, "_id": id}}
        suggestion = self.suggestion_builder.build(id, dict(doc))
        return op, suggestion

    def _get_index_name(self, file_name) -> str:
        timestamp = int(time.time())
        if "/" in file_name:
            _, file_name = file_name.rsplit("/", 1)
        base_name = "-".join(file_name.split("-")[:2])
        return f"{base_name}-{self.index_version}-{timestamp}"

    def _create_index(self, index_name: str) -> bool:
        exists = self.elasticsearch.index_exists(index=index_name)

        version_settings = get_settings_for_version(self.index_version)
        language = self.file_manager.language  # e.g "fr"

        if not exists and version_settings:
            logger.info(f"Creating index for language: {language}")

            return self.elasticsearch.create_index(
                index=index_name,
                mappings=get_suggest_mapping(language),
                settings=get_suggest_settings(language),
            )

        return False

    def _apply_active_lifecycle_policy(self, index_name: str):
        """Attach the never-delete ILM policy to the newly built index."""
        policy = ACTIVE_ILM_POLICY.format(language=self.file_manager.language)
        self.elasticsearch.set_index_lifecycle_policy(index=index_name, policy=policy)
        logger.info(
            "Applied active lifecycle policy",
            extra={"index": index_name, "policy": policy},
        )

    def _apply_backup_lifecycle_policies(self, alias: str):
        """Attach the expiring ILM policy to every superseded index.

        Indices still served by `alias` keep the active policy. Indices that already
        carry the backup policy are skipped so a rerun is a no-op for them.
        """
        language = self.file_manager.language
        policy = BACKUP_ILM_POLICY.format(language=language)
        pattern = INDEX_PATTERN.format(language=language, version=self.index_version)

        active = set(self.elasticsearch.get_indices_for_alias(alias=alias))
        current = self.elasticsearch.get_index_lifecycle_policies(index=pattern)

        for index, current_policy in current.items():
            if index in active or current_policy == policy:
                continue
            self.elasticsearch.set_index_lifecycle_policy(index=index, policy=policy)
            logger.info(
                "Applied backup lifecycle policy",
                extra={
                    "index": index,
                    "policy": policy,
                    "previous_policy": current_policy,
                },
            )

    def _wait_for_followers(self, index_name: str, cloned_at: float | None = None) -> None:
        """Block until every CCR follower of `index_name` has replicated all of it.

        Followers are discovered from the retention leases they hold on the leader's
        primary shards, so only the leader cluster is queried. Auto-follow only creates
        a follower after noticing the new index, so leases are collected for at least
        `follower_discovery_period` before concluding which followers exist. A
        follower has caught up on a shard once its lease retains nothing at or below
        the leader's global checkpoint. Leases are renewed periodically (every 30s by
        default), so they may trail the follower's actual progress but never run
        ahead of it.

        Each follower is logged when first discovered, with the seconds since
        `cloned_at` (a `time.monotonic()` reading, defaulting to the start of the wait).
        That is how long auto-follow took to pick up the index, to within one poll
        interval, and informs the choice of `follower_discovery_period`.

        Raises:
            TimeoutError: If followers have not caught up within `follower_sync_timeout`.
        """
        start = time.monotonic()
        if cloned_at is None:
            cloned_at = start
        discovered: set[str] = set()
        while True:
            followers, lagging = self._get_follower_progress(index_name)
            now = time.monotonic()
            for follower in sorted(followers - discovered):
                logger.info(
                    "Discovered follower",
                    extra={
                        "index": index_name,
                        "follower": follower,
                        "seconds_since_clone": round(now - cloned_at, 1),
                    },
                )
            discovered |= followers
            elapsed = now - start
            if not lagging and elapsed >= self.follower_discovery_period:
                logger.info(
                    "Followers are in sync" if followers else "Index has no followers",
                    extra={"index": index_name, "followers": sorted(followers)},
                )
                return
            if elapsed >= self.follower_sync_timeout:
                raise TimeoutError(
                    f"Followers of {index_name} did not catch up within "
                    f"{self.follower_sync_timeout}s: {sorted(lagging)}"
                )
            logger.info(
                "Waiting for followers",
                extra={
                    "index": index_name,
                    "followers": sorted(followers),
                    "lagging_followers": sorted(lagging),
                },
            )
            time.sleep(self.follower_sync_poll_interval)

    def _get_follower_progress(self, index_name: str) -> tuple[set[str], set[str]]:
        """Return the CCR follower lease IDs on `index_name` and the subset still behind."""
        followers: set[str] = set()
        lagging: set[str] = set()
        for copies in self.elasticsearch.get_shard_stats(index=index_name).values():
            primary = next(copy for copy in copies if copy["routing"]["primary"])
            global_checkpoint = primary["seq_no"]["global_checkpoint"]
            for lease in primary["retention_leases"]["leases"]:
                if lease["source"] != CCR_RETENTION_LEASE_SOURCE:
                    continue
                followers.add(lease["id"])
                if lease["retaining_seq_no"] <= global_checkpoint:
                    lagging.add(lease["id"])
        return followers, lagging

    def _flip_alias_to_latest(self, current_index: str, alias: str) -> str:
        """Point `alias` at `current_index` only, and return the resolved alias."""
        alias = alias.format(version=self.index_version)

        # fetch previous index using alias so we know what to delete
        actions: list[dict[str, Any]] = [{"add": {"index": current_index, "alias": alias}}]

        if self.elasticsearch.alias_exists(alias=alias):
            indices = self.elasticsearch.get_indices_for_alias(alias=alias)
            for idx in indices:
                logger.info(
                    "adding index to be removed from alias",
                    extra={"index": idx, "alias": alias},
                )
                actions.append({"remove": {"index": idx, "alias": alias}})

        self.elasticsearch.update_aliases(actions=actions)
        return alias
