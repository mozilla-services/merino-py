"""Unit tests for merino_hook_eye.ccr.metrics."""

from typing import Any

import pytest
from merino_common.testing.metrics import find_point, number_points
from opentelemetry.sdk.metrics.export import InMemoryMetricReader, Sum

from merino_hook_eye.ccr import metrics as ccr_metrics
from merino_hook_eye.ccr.stats import parse_ccr_stats

_PATTERNS = ["*wiki-*", "*sports-*"]

_SHARD_METRICS = {
    "merino.ccr.follower_aliases_version": 4,
    "merino.ccr.follower_settings_version": 3,
    "merino.ccr.time_since_last_read_ms": 250,
    "merino.ccr.failed_read_requests": 2,
    "merino.ccr.leader_global_checkpoint": 1024,
    "merino.ccr.follower_global_checkpoint": 1019,
}

_ALL_CCR_METRICS = [
    "merino.ccr.auto_follow.failed_remote_cluster_state_requests",
    "merino.ccr.auto_follow.time_since_last_check_ms",
    "merino.ccr.auto_follow.failed_follow_indices",
    *_SHARD_METRICS,
]


@pytest.fixture
def published(ccr_stats_body: dict[str, Any]) -> None:
    """Publish the sample `_ccr/stats` response as the current snapshot."""
    ccr_metrics.publish(parse_ccr_stats(ccr_stats_body, _PATTERNS))


@pytest.mark.usefixtures("published")
def test_auto_follow_metrics(metric_reader: InMemoryMetricReader) -> None:
    """The auto-follow coordinator's stats are reported from the snapshot."""
    failed_requests = number_points(
        metric_reader, "merino.ccr.auto_follow.failed_remote_cluster_state_requests"
    )
    failed_indices = number_points(metric_reader, "merino.ccr.auto_follow.failed_follow_indices")
    last_check = find_point(
        metric_reader,
        "merino.ccr.auto_follow.time_since_last_check_ms",
        remote_cluster="leader",
    )

    assert [point.value for point in failed_requests] == [3]
    assert [point.value for point in failed_indices] == [1]
    assert last_check is not None and last_check.value == 1200


@pytest.mark.usefixtures("published")
@pytest.mark.parametrize(
    ("name", "expected"), list(_SHARD_METRICS.items()), ids=list(_SHARD_METRICS)
)
def test_shard_metrics(metric_reader: InMemoryMetricReader, name: str, expected: int) -> None:
    """Each shard metric is reported per follower shard, labelled by index and shard."""
    point = find_point(
        metric_reader, name, remote_cluster="leader", index="enwiki-202611250000", shard="0"
    )
    indices = {(p.attributes or {}).get("index") for p in number_points(metric_reader, name)}

    assert point is not None and point.value == expected
    assert len(number_points(metric_reader, name)) == 3
    assert indices == {"enwiki-202611250000", "sports-en-event"}


@pytest.mark.usefixtures("published")
def test_running_totals_are_cumulative_counters(metric_reader: InMemoryMetricReader) -> None:
    """Elasticsearch's running totals are exported as monotonic cumulative sums."""
    data = metric_reader.get_metrics_data()
    assert data is not None
    exported = {
        metric.name: metric.data
        for resource in data.resource_metrics
        for scope in resource.scope_metrics
        for metric in scope.metrics
    }

    for name in (
        "merino.ccr.auto_follow.failed_remote_cluster_state_requests",
        "merino.ccr.failed_read_requests",
    ):
        exported_data = exported[name]
        assert isinstance(exported_data, Sum)
        assert exported_data.is_monotonic


@pytest.mark.parametrize("name", _ALL_CCR_METRICS)
def test_no_series_without_snapshot(metric_reader: InMemoryMetricReader, name: str) -> None:
    """Nothing is reported before the first scrape or after a failed one."""
    assert ccr_metrics.latest() is None
    assert number_points(metric_reader, name) == []


@pytest.mark.usefixtures("published")
def test_clear_stops_reporting(metric_reader: InMemoryMetricReader) -> None:
    """Clearing the snapshot stops every CCR series instead of repeating stale values."""
    assert number_points(metric_reader, "merino.ccr.follower_global_checkpoint")

    ccr_metrics.clear()

    assert number_points(metric_reader, "merino.ccr.follower_global_checkpoint") == []
