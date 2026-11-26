"""Unit tests for merino_hook_eye.ccr.stats."""

from typing import Any

import pytest
from pydantic import ValidationError

from merino_hook_eye.ccr.stats import (
    AutoFollowedCluster,
    ShardFollowStats,
    parse_ccr_stats,
)

_PATTERNS = ["*wiki-*", "*sports-*"]


def test_parse_auto_follow_stats(ccr_stats_body: dict[str, Any]) -> None:
    """The auto-follow counts and per remote cluster check times are parsed."""
    stats = parse_ccr_stats(ccr_stats_body, _PATTERNS)

    assert stats.auto_follow.number_of_failed_follow_indices == 1
    assert stats.auto_follow.number_of_failed_remote_cluster_state_requests == 3
    assert stats.auto_follow.auto_followed_clusters == (
        AutoFollowedCluster(cluster_name="leader", time_since_last_check_ms=1200),
    )


def test_parse_shard_stats(ccr_stats_body: dict[str, Any]) -> None:
    """Every shard of a matching follower index is parsed with its replication stats."""
    stats = parse_ccr_stats(ccr_stats_body, _PATTERNS)

    assert stats.shards[0] == ShardFollowStats(
        remote_cluster="leader",
        leader_index="enwiki-202611250000",
        follower_index="enwiki-202611250000",
        shard_id=0,
        leader_global_checkpoint=1024,
        follower_global_checkpoint=1019,
        follower_aliases_version=4,
        follower_settings_version=3,
        time_since_last_read_ms=250,
        failed_read_requests=2,
    )


@pytest.mark.parametrize(
    ("patterns", "expected"),
    [
        (
            _PATTERNS,
            [("enwiki-202611250000", 0), ("enwiki-202611250000", 1), ("sports-en-event", 0)],
        ),
        (["sports-*"], [("sports-en-event", 0)]),
        (
            ["*"],
            [
                ("enwiki-202611250000", 0),
                ("enwiki-202611250000", 1),
                ("sports-en-event", 0),
                ("unrelated-index", 0),
            ],
        ),
        (["nothing-*"], []),
    ],
    ids=["defaults", "sports-only", "everything", "no-match"],
)
def test_parse_filters_indices(
    ccr_stats_body: dict[str, Any],
    patterns: list[str],
    expected: list[tuple[str, int]],
) -> None:
    """Only shards of follower indices matching an index pattern are kept."""
    stats = parse_ccr_stats(ccr_stats_body, patterns)

    assert [(shard.follower_index, shard.shard_id) for shard in stats.shards] == expected


def test_parse_without_followers() -> None:
    """A cluster that follows nothing yet parses to empty collections."""
    body = {
        "auto_follow_stats": {
            "number_of_failed_follow_indices": 0,
            "number_of_failed_remote_cluster_state_requests": 0,
        },
        "follow_stats": {},
    }

    stats = parse_ccr_stats(body, _PATTERNS)

    assert stats.auto_follow.auto_followed_clusters == ()
    assert stats.shards == ()


def test_parse_rejects_malformed_body(ccr_stats_body: dict[str, Any]) -> None:
    """A body missing a reported field raises rather than reporting partial data."""
    del ccr_stats_body["follow_stats"]["indices"][0]["shards"][0]["follower_global_checkpoint"]

    with pytest.raises(ValidationError):
        parse_ccr_stats(ccr_stats_body, _PATTERNS)
