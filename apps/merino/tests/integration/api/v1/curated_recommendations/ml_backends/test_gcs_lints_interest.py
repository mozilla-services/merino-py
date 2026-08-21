"""Integration tests for the LinTS-interest GCS backend."""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Callable

import numpy as np
import pytest
from aiodogstatsd import Client as StatsdClient
from google.cloud.storage import Bucket, Client
from safetensors.numpy import save

from merino.configs import settings
from merino.curated_recommendations.corpus_backends.protocol import SurfaceId
from merino.curated_recommendations.ml_backends.lints_interest_model import (
    LinTSInterestBackend,
    L_FORMAT_LAPACK_LOWER_PACKED,
    SCHEMA_VERSION,
)
from merino.utils.synced_gcs_blob import SyncedGcsBlob


# -----------------------------------------------------------------------------
# Bundle builder
# -----------------------------------------------------------------------------
def _pack_lower_lapack(L_dense: np.ndarray) -> np.ndarray:
    """Dense lower-triangular → LAPACK column-major lower-packed."""
    d = L_dense.shape[0]
    out = np.empty(d * (d + 1) // 2, dtype=L_dense.dtype)
    offset = 0
    for j in range(d):
        n_col = d - j
        out[offset : offset + n_col] = L_dense[j:, j]
        offset += n_col
    return out


def _build_synthetic_bundle(*, n_items: int = 5, n_topics: int = 7) -> bytes:
    """Assemble a small but well-formed. Returns the safetensors bytes."""
    rng = np.random.default_rng(0)
    bias_idx = 0
    topic_main_to_idx = {t: 1 + t for t in range(n_topics)}

    item_to_idx: dict[str, int] = {}
    item_topic_to_idx: dict[tuple[str, int], int] = {}
    next_idx = 1 + n_topics
    for i in range(n_items):
        item_to_idx[f"item_{i:02d}"] = next_idx
        next_idx += 1
    for i in range(n_items):
        for t in range(min(3, n_topics)):
            item_topic_to_idx[(f"item_{i:02d}", t)] = next_idx
            next_idx += 1
    d = next_idx

    M = rng.standard_normal((d, d)).astype(np.float32)
    A = (M @ M.T).astype(np.float32) + (d * np.eye(d, dtype=np.float32))
    L_dense = np.linalg.cholesky(A).astype(np.float32)
    theta_hat = (rng.standard_normal(d) * 0.001).astype(np.float32)

    metadata: dict[str, str] = {
        "schema_version": SCHEMA_VERSION,
        "model_id": "inferred-v3-model",
        "epoch_id": datetime.now(timezone.utc).strftime("%Y%m%d-%H%M"),
        "dim": str(d),
        "v": "0.005",
        "n_topics": str(n_topics),
        "topic_names": json.dumps([f"topic_{t}" for t in range(n_topics)]),
        "thresholds": json.dumps([[0.25, 0.46, 0.8]] * n_topics),
        "bias_idx": str(bias_idx),
        "L_format": L_FORMAT_LAPACK_LOWER_PACKED,
        "topic_main_to_idx": json.dumps({str(t): idx for t, idx in topic_main_to_idx.items()}),
        "item_to_idx": json.dumps(item_to_idx),
        "item_topic_to_idx": json.dumps(
            {f"{iid}|{t}": idx for (iid, t), idx in item_topic_to_idx.items()}
        ),
    }
    return save(
        {"L_lower": _pack_lower_lapack(L_dense), "theta_hat": theta_hat},
        metadata=metadata,
    )


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------
@pytest.fixture(scope="function")
def gcs_bucket(gcs_storage_client):
    """Create a fake-GCS bucket for the LinTS-interest blob."""
    bucket = gcs_storage_client.create_bucket(settings.contextual_interest.gcs.bucket_name)
    yield bucket
    bucket.delete(force=True)


def _create_backend(
    gcs_storage_client: Client, gcs_bucket: Bucket, metrics_client: StatsdClient
) -> LinTSInterestBackend:
    """Build a real LinTSInterestBackend pointed at the fake-GCS bucket."""
    synced_gcs_blob = SyncedGcsBlob(
        storage_client=gcs_storage_client,
        bucket_name=gcs_bucket.name,
        blob_name=settings.contextual_interest.gcs.blob_name,
        metrics_client=metrics_client,
        metrics_namespace="recommendation.ml.lints_interest",
        max_size=settings.contextual_interest.gcs.max_size,
        cron_interval_seconds=0.01,
        cron_job_name="fetch_lints_interest_model",
        is_bytes=True,
    )
    synced_gcs_blob.initialize()
    return LinTSInterestBackend(synced_gcs_blobs={SurfaceId.NEW_TAB_EN_US: synced_gcs_blob})


def _create_blob(bucket: Bucket, data: bytes):
    """Upload bytes as the lints_interest blob."""
    blob = bucket.blob(settings.contextual_interest.gcs.blob_name)
    blob.upload_from_string(data=data, content_type="application/octet-stream")
    return blob


async def wait(until: Callable[[], bool]) -> None:
    """Wait up to 2s for a condition to be true."""
    max_wait_sec = 2
    start = time.time()
    while time.time() - start < max_wait_sec:
        if until():
            break
        await asyncio.sleep(0.01)


async def wait_until_loaded(backend: LinTSInterestBackend) -> None:
    """Wait until the backend has done at least one fetch from GCS."""
    await wait(until=lambda: backend.update_count > 0)


@pytest.fixture
def good_blob(gcs_bucket):
    """Upload a well-formed synthetic bundle."""
    return _create_blob(gcs_bucket, _build_synthetic_bundle())


@pytest.fixture
def large_blob(gcs_bucket):
    """Upload a blob exceeding contextual_interest.gcs.max_size."""
    return _create_blob(gcs_bucket, b"a" * (settings.contextual_interest.gcs.max_size + 1))


# -----------------------------------------------------------------------------
# Tests
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_load_well_formed_bundle(
    gcs_storage_client, gcs_bucket, metrics_client, good_blob
) -> None:
    """A bundle in GCS gets fetched, parsed, and is_valid returns True."""
    backend = _create_backend(gcs_storage_client, gcs_bucket, metrics_client)
    await wait_until_loaded(backend)

    assert backend.is_valid(SurfaceId.NEW_TAB_EN_US)
    # Items declared in the bundle should be looked up successfully.
    assert backend.has_item(SurfaceId.NEW_TAB_EN_US, "item_00")
    assert not backend.has_item(SurfaceId.NEW_TAB_EN_US, "never_indexed")


@pytest.mark.asyncio
async def test_score_request_after_gcs_load(
    gcs_storage_client, gcs_bucket, metrics_client, good_blob
) -> None:
    """End-to-end: load from GCS, then sample θ̃ via stpsv against the loaded
    state. Confirms the on-disk → in-memory → score path is fully wired.
    """
    backend = _create_backend(gcs_storage_client, gcs_bucket, metrics_client)
    await wait_until_loaded(backend)

    rng = np.random.default_rng(42)
    scores = backend.score_request(
        SurfaceId.NEW_TAB_EN_US,
        strengths={f"topic_{t}": 0.5 for t in range(3)},
        candidate_item_ids=[f"item_{i:02d}" for i in range(5)],
        rng=rng,
    )
    assert scores.shape == (5,)
    assert np.all(np.isfinite(scores))


@pytest.mark.asyncio
async def test_logs_error_for_oversized_blob(
    gcs_storage_client, gcs_bucket, metrics_client, large_blob, caplog
) -> None:
    """SyncedGcsBlob refuses to download a blob exceeding ``max_size``; the
    backend stays invalid and an error is logged.
    """
    backend = _create_backend(gcs_storage_client, gcs_bucket, metrics_client)
    caplog.set_level(logging.ERROR)
    # The fetch task runs even when oversize → wait briefly so the cron tick
    # has a chance to log.
    await wait(until=lambda: any("exceeds" in r.message for r in caplog.records))

    assert any("exceeds" in r.message for r in caplog.records)
    assert not backend.is_valid(SurfaceId.NEW_TAB_EN_US)


@pytest.mark.asyncio
async def test_corrupt_bundle_keeps_backend_invalid(
    gcs_storage_client, gcs_bucket, metrics_client, caplog
) -> None:
    """Garbage bytes at the blob location → fetch_callback raises internally,
    is logged, and the backend stays invalid (no false positive).
    """
    _create_blob(gcs_bucket, b"definitely-not-safetensors")
    caplog.set_level(logging.ERROR)
    backend = _create_backend(gcs_storage_client, gcs_bucket, metrics_client)
    await wait_until_loaded(backend)

    assert not backend.is_valid(SurfaceId.NEW_TAB_EN_US)
    assert any("failed to parse bundle" in r.message.lower() for r in caplog.records)
