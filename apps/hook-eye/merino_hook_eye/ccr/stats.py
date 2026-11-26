"""Typed view of the parts of `GET _ccr/stats` that merino-hook-eye reports.

The Elasticsearch Python client returns this response untyped, so these models describe the
fields behind the emitted metrics; other fields are ignored. See
https://www.elastic.co/guide/en/elasticsearch/reference/8.18/ccr-get-stats.html for the full
response.
"""

from fnmatch import fnmatchcase
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _Model(BaseModel):
    """Immutable model that ignores unknown fields and accepts field names or ES aliases."""

    model_config = ConfigDict(frozen=True, validate_by_name=True, validate_by_alias=True)


class AutoFollowedCluster(_Model):
    """Auto-follow coordinator state for one remote (leader) cluster."""

    cluster_name: str = Field(description="Name of the remote (leader) cluster")
    time_since_last_check_ms: int = Field(
        validation_alias="time_since_last_check_millis",
        description="Milliseconds since the coordinator last checked this remote cluster",
    )


class AutoFollowStats(_Model):
    """Stats of the auto-follow coordinator, which runs on the elected master node.

    Both counts accumulate from when that node became master, so they reset on a master
    change.
    """

    number_of_failed_follow_indices: int = Field(
        description="Leader indices the coordinator failed to follow"
    )
    number_of_failed_remote_cluster_state_requests: int = Field(
        description="Times the coordinator failed to fetch a remote cluster state"
    )
    auto_followed_clusters: tuple[AutoFollowedCluster, ...] = Field(
        default=(), description="Remote clusters the coordinator checks"
    )


class ShardFollowStats(_Model):
    """Replication stats of one shard of a follower index."""

    remote_cluster: str = Field(description="Name of the remote (leader) cluster")
    leader_index: str = Field(description="Name of the leader index")
    follower_index: str = Field(description="Name of the follower index")
    shard_id: int = Field(description="Shard number within the index")
    leader_global_checkpoint: int = Field(
        description="Leader shard global checkpoint, as last seen by the follower"
    )
    follower_global_checkpoint: int = Field(description="Follower shard global checkpoint")
    follower_aliases_version: int = Field(description="Aliases version of the follower shard")
    follower_settings_version: int = Field(description="Settings version of the follower shard")
    time_since_last_read_ms: int = Field(
        validation_alias="time_since_last_read_millis",
        description="Milliseconds since the follower shard last read from its leader",
    )
    failed_read_requests: int = Field(
        description="Failed read requests from the follower shard to its leader"
    )


class _FollowerIndex(_Model):
    """One entry of `follow_stats.indices`."""

    index: str = Field(description="Name of the follower index")
    shards: tuple[ShardFollowStats, ...] = Field(
        default=(), description="Stats of each shard of the follower index"
    )


class _FollowStats(_Model):
    """The `follow_stats` section."""

    indices: tuple[_FollowerIndex, ...] = Field(
        default=(), description="Follower indices on this cluster"
    )


class _CcrStatsResponse(_Model):
    """The `GET _ccr/stats` response body."""

    auto_follow_stats: AutoFollowStats = Field(description="Auto-follow coordinator stats")
    follow_stats: _FollowStats = Field(description="Shard-follow task stats")


class CcrStats(_Model):
    """The reported parts of a `GET _ccr/stats` response."""

    auto_follow: AutoFollowStats = Field(description="Auto-follow coordinator stats")
    shards: tuple[ShardFollowStats, ...] = Field(
        description="Shards of the follower indices selected for reporting"
    )


def parse_ccr_stats(body: dict[str, Any], index_patterns: list[str]) -> CcrStats:
    """Parse a `GET _ccr/stats` response body.

    Args:
        body: The decoded JSON response.
        index_patterns: fnmatch patterns; only shards of follower indices matching one of
            them are kept.

    Raises:
        pydantic.ValidationError: If the body lacks a field or holds an unexpected type.
    """
    response = _CcrStatsResponse.model_validate(body)
    return CcrStats(
        auto_follow=response.auto_follow_stats,
        shards=tuple(
            shard
            for index in response.follow_stats.indices
            if any(fnmatchcase(index.index, pattern) for pattern in index_patterns)
            for shard in index.shards
        ),
    )
