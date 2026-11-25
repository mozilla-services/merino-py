"""OpenTelemetry instruments for the CCR monitor.

Values come from the latest successful `_ccr/stats` scrape; `clear()` drops them when a scrape
fails. See `merino_hook_eye.metrics` for why they're observable.
"""

from collections.abc import Callable, Iterable

from opentelemetry.metrics import CallbackOptions, Observation

from merino_hook_eye.ccr.stats import CcrStats, ShardFollowStats
from merino_hook_eye.metrics import meter as _meter

_latest: CcrStats | None = None


def publish(stats: CcrStats) -> None:
    """Make `stats` the snapshot reported on every following metric collection."""
    global _latest
    _latest = stats


def clear() -> None:
    """Drop the current snapshot, so no CCR series is reported until the next `publish`."""
    global _latest
    _latest = None


def latest() -> CcrStats | None:
    """Return the snapshot currently being reported, if any."""
    return _latest


def _shard_attributes(shard: ShardFollowStats) -> dict[str, str]:
    """Return the attributes identifying a follower shard's series."""
    return {
        "remote_cluster": shard.remote_cluster,
        "index": shard.follower_index,
        "shard": str(shard.shard_id),
    }


def _observe_failed_remote_cluster_state_requests(
    options: CallbackOptions,
) -> Iterable[Observation]:
    """Report the auto-follow coordinator's failed remote cluster state requests."""
    if _latest is None:
        return []
    return [Observation(_latest.auto_follow.number_of_failed_remote_cluster_state_requests)]


def _observe_failed_follow_indices(options: CallbackOptions) -> Iterable[Observation]:
    """Report the number of indices the auto-follow coordinator failed to follow."""
    if _latest is None:
        return []
    return [Observation(_latest.auto_follow.number_of_failed_follow_indices)]


def _observe_time_since_last_check(options: CallbackOptions) -> Iterable[Observation]:
    """Report, per remote cluster, the time since the auto-follow coordinator checked it."""
    if _latest is None:
        return []
    return [
        Observation(cluster.time_since_last_check_ms, {"remote_cluster": cluster.cluster_name})
        for cluster in _latest.auto_follow.auto_followed_clusters
    ]


def _shard_callback(
    value: Callable[[ShardFollowStats], int],
) -> Callable[[CallbackOptions], Iterable[Observation]]:
    """Build a callback reporting `value` for every tracked follower shard."""

    def callback(options: CallbackOptions) -> Iterable[Observation]:
        if _latest is None:
            return []
        return [Observation(value(shard), _shard_attributes(shard)) for shard in _latest.shards]

    return callback


_meter.create_observable_counter(
    "merino.ccr.auto_follow.failed_remote_cluster_state_requests",
    callbacks=[_observe_failed_remote_cluster_state_requests],
    description="Times the auto-follow coordinator failed to fetch a remote cluster state",
)
_meter.create_observable_gauge(
    "merino.ccr.auto_follow.time_since_last_check_ms",
    callbacks=[_observe_time_since_last_check],
    unit="ms",
    description="Time since the auto-follow coordinator last checked a remote cluster",
)
_meter.create_observable_gauge(
    "merino.ccr.auto_follow.failed_follow_indices",
    callbacks=[_observe_failed_follow_indices],
    description="Indices the auto-follow coordinator failed to follow",
)
_meter.create_observable_gauge(
    "merino.ccr.follower_aliases_version",
    callbacks=[_shard_callback(lambda shard: shard.follower_aliases_version)],
    description="Aliases version of the follower shard",
)
_meter.create_observable_gauge(
    "merino.ccr.follower_settings_version",
    callbacks=[_shard_callback(lambda shard: shard.follower_settings_version)],
    description="Settings version of the follower shard",
)
_meter.create_observable_gauge(
    "merino.ccr.time_since_last_read_ms",
    callbacks=[_shard_callback(lambda shard: shard.time_since_last_read_ms)],
    unit="ms",
    description="Time since the follower shard last sent a read request to its leader",
)
_meter.create_observable_counter(
    "merino.ccr.failed_read_requests",
    callbacks=[_shard_callback(lambda shard: shard.failed_read_requests)],
    description="Failed read requests from the follower shard to its leader",
)
_meter.create_observable_gauge(
    "merino.ccr.leader_global_checkpoint",
    callbacks=[_shard_callback(lambda shard: shard.leader_global_checkpoint)],
    description="Leader shard global checkpoint, as last seen by the follower",
)
_meter.create_observable_gauge(
    "merino.ccr.follower_global_checkpoint",
    callbacks=[_shard_callback(lambda shard: shard.follower_global_checkpoint)],
    description="Follower shard global checkpoint",
)

scrape_counter = _meter.create_counter(
    "merino.ccr.scrape",
    description="Scrapes of GET _ccr/stats, by outcome",
)
