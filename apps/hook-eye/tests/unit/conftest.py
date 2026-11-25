"""Shared test configuration for merino-hook-eye.

Must set MERINO_HOOK_EYE_ENV before any merino_hook_eye import.
"""

import copy
import logging
import os
from typing import Any

import pytest
from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

os.environ.setdefault("MERINO_HOOK_EYE_ENV", "testing")

# Modeled on the ES 8.18 `GET _ccr/stats` reference response, trimmed to fewer fields. Holds a
# followed wiki index with two shards, a followed sports index, and an index no default pattern
# matches.
_CCR_STATS_BODY: dict[str, Any] = {
    "auto_follow_stats": {
        "number_of_failed_follow_indices": 1,
        "number_of_failed_remote_cluster_state_requests": 3,
        "number_of_successful_follow_indices": 4,
        "recent_auto_follow_errors": [],
        "auto_followed_clusters": [
            {
                "cluster_name": "leader",
                "time_since_last_check_millis": 1200,
                "last_seen_metadata_version": 28,
            }
        ],
    },
    "follow_stats": {
        "indices": [
            {
                "index": "enwiki-202611250000",
                "total_global_checkpoint_lag": 5,
                "shards": [
                    {
                        "remote_cluster": "leader",
                        "leader_index": "enwiki-202611250000",
                        "follower_index": "enwiki-202611250000",
                        "shard_id": 0,
                        "leader_global_checkpoint": 1024,
                        "leader_max_seq_no": 1024,
                        "follower_global_checkpoint": 1019,
                        "follower_max_seq_no": 1019,
                        "follower_mapping_version": 2,
                        "follower_settings_version": 3,
                        "follower_aliases_version": 4,
                        "failed_read_requests": 2,
                        "read_exceptions": [],
                        "time_since_last_read_millis": 250,
                    },
                    {
                        "remote_cluster": "leader",
                        "leader_index": "enwiki-202611250000",
                        "follower_index": "enwiki-202611250000",
                        "shard_id": 1,
                        "leader_global_checkpoint": 900,
                        "leader_max_seq_no": 900,
                        "follower_global_checkpoint": 900,
                        "follower_max_seq_no": 900,
                        "follower_mapping_version": 2,
                        "follower_settings_version": 3,
                        "follower_aliases_version": 4,
                        "failed_read_requests": 0,
                        "read_exceptions": [],
                        "time_since_last_read_millis": 300,
                    },
                ],
            },
            {
                "index": "sports-en-event",
                "total_global_checkpoint_lag": 0,
                "shards": [
                    {
                        "remote_cluster": "leader",
                        "leader_index": "sports-en-event",
                        "follower_index": "sports-en-event",
                        "shard_id": 0,
                        "leader_global_checkpoint": 77,
                        "follower_global_checkpoint": 77,
                        "follower_settings_version": 1,
                        "follower_aliases_version": 1,
                        "failed_read_requests": 0,
                        "read_exceptions": [],
                        "time_since_last_read_millis": 10,
                    }
                ],
            },
            {
                "index": "unrelated-index",
                "total_global_checkpoint_lag": 0,
                "shards": [
                    {
                        "remote_cluster": "leader",
                        "leader_index": "unrelated-index",
                        "follower_index": "unrelated-index",
                        "shard_id": 0,
                        "leader_global_checkpoint": 1,
                        "follower_global_checkpoint": 1,
                        "follower_settings_version": 1,
                        "follower_aliases_version": 1,
                        "failed_read_requests": 0,
                        "read_exceptions": [],
                        "time_since_last_read_millis": 10,
                    }
                ],
            },
        ]
    },
}


@pytest.fixture
def ccr_stats_body() -> dict[str, Any]:
    """Return a fresh, mutable copy of a sample `GET _ccr/stats` response body."""
    return copy.deepcopy(_CCR_STATS_BODY)


@pytest.fixture(scope="session")
def metric_reader() -> InMemoryMetricReader:
    """Install a process-global MeterProvider once and expose its reader.

    OpenTelemetry only honors the first `set_meter_provider()` call per process, so the
    provider must be configured a single time and shared across tests. The proxy instruments
    created at import time rebind to this provider on the first set. Synchronous counters
    accumulate across the session; assert on deltas rather than absolute values.
    """
    reader = InMemoryMetricReader()
    metrics.set_meter_provider(MeterProvider(metric_readers=[reader]))
    return reader


@pytest.fixture(autouse=True)
def _reset_snapshot() -> None:
    """Start every test without a published CCR snapshot."""
    from merino_hook_eye.ccr import metrics as ccr_metrics

    ccr_metrics.clear()


@pytest.fixture(autouse=True)
def _propagate_logger(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force the merino-hook-eye loggers to propagate so `caplog` can capture records.

    `configure_logging(..., can_propagate=False)` elsewhere in the session would otherwise
    block records from reaching the root logger where `caplog` listens.
    """
    monkeypatch.setattr(logging.getLogger("merino_hook_eye"), "propagate", True)
