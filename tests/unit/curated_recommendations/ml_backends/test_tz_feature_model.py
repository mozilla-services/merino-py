"""Unit tests for the TZFeatureBackend.

Builds a synthetic ``tz_ratios_v1`` safetensors bundle in-memory (same byte
layout the ml-services inference flow produces), feeds it through
``_fetch_callback``, and verifies:

  - happy-path load + lookup
  - baseline tz_index returns exactly 1.0
  - unknown item / out-of-range tz_index return ``None``
  - schema-version mismatch → existing state preserved (load is a no-op)
  - clipping at safe band on load
  - cache time expiry triggers ``is_valid`` -> False
  - empty stub backend always reports invalid + None
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import numpy as np
import pytest
from safetensors.numpy import save

from merino.curated_recommendations.corpus_backends.protocol import SurfaceId
from merino.curated_recommendations.ml_backends.tz_feature_model import (
    EmptyTZFeatureBackend,
    SAFE_RATIO_HIGH,
    SAFE_RATIO_LOW,
    SCHEMA_VERSION,
    TZFeatureBackend,
    VALIDITY_PERIOD_MINUTES,
)


def _build_bundle(
    item_ids: list[str],
    ratios: np.ndarray,
    tz_labels: list[str] | None = None,
    baseline_tz: str = "ET",
    schema_version: str = SCHEMA_VERSION,
    epoch_id: str | None = None,
) -> bytes:
    """Build a safetensors bundle matching the inference flow's byte layout."""
    if tz_labels is None:
        tz_labels = ["PT", "MT", "CT", "ET"]
    if epoch_id is None:
        epoch_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    metadata = {
        "schema_version": schema_version,
        "epoch_id": epoch_id,
        "locale": "EN_US",
        "surface_id": "NEW_TAB_EN_US",
        "inferred_model_id": "inferred-v3-model",
        "tz_labels": json.dumps(tz_labels),
        "baseline_tz": baseline_tz,
        "non_baseline_tzs": json.dumps([t for t in tz_labels if t != baseline_tz]),
        "ratio_clip_low": "0.5",
        "ratio_clip_high": "2.0",
        "n_items": str(len(item_ids)),
        "item_to_idx": json.dumps({iid: i for i, iid in enumerate(item_ids)}),
        "model_epoch_id": "20260101-0000",
    }
    return save({"ratios": ratios.astype(np.float32)}, metadata=metadata)


def _make_backend(synced_blob_mock: MagicMock | None = None) -> TZFeatureBackend:
    blob = synced_blob_mock or MagicMock()
    return TZFeatureBackend(synced_gcs_blobs={SurfaceId.NEW_TAB_EN_US: blob})


# -----------------------------------------------------------------------------
# Happy path: load + lookup
# -----------------------------------------------------------------------------
def test_happy_path_load_and_lookup() -> None:
    """A well-formed bundle loads and lookups return the right per-(item, tz) ratio."""
    item_ids = ["item_A", "item_B"]
    ratios = np.array(
        [
            [1.2, 0.8, 0.9, 1.0],  # item_A: prefers PT
            [0.7, 1.1, 1.3, 1.0],  # item_B: prefers CT
        ],
        dtype=np.float32,
    )
    bundle = _build_bundle(item_ids, ratios)
    backend = _make_backend()
    backend._fetch_callback(bundle, surface_id=SurfaceId.NEW_TAB_EN_US)

    assert backend.is_valid(SurfaceId.NEW_TAB_EN_US) is True
    assert backend.get_ratio(SurfaceId.NEW_TAB_EN_US, "item_A", tz_index=0) == pytest.approx(1.2)
    assert backend.get_ratio(SurfaceId.NEW_TAB_EN_US, "item_B", tz_index=2) == pytest.approx(1.3)


def test_baseline_tz_returns_one() -> None:
    """tz_index pointing at the baseline TZ (ET) returns exactly 1.0."""
    item_ids = ["item_A"]
    # Even if the publisher accidentally wrote something other than 1.0 in the
    # baseline column, the backend returns 1.0 explicitly so the contract is
    # never ambiguous for ET users.
    ratios = np.array([[1.5, 0.7, 0.9, 0.42]], dtype=np.float32)
    bundle = _build_bundle(item_ids, ratios)
    backend = _make_backend()
    backend._fetch_callback(bundle, surface_id=SurfaceId.NEW_TAB_EN_US)

    # ET is at column 3 in the default tz_labels list.
    assert backend.get_ratio(SurfaceId.NEW_TAB_EN_US, "item_A", tz_index=3) == 1.0


def test_unknown_item_returns_none() -> None:
    """Items not in item_to_idx return None — caller skips the adjustment."""
    bundle = _build_bundle(["known"], np.array([[1.1, 0.9, 1.0, 1.0]], dtype=np.float32))
    backend = _make_backend()
    backend._fetch_callback(bundle, surface_id=SurfaceId.NEW_TAB_EN_US)

    assert backend.get_ratio(SurfaceId.NEW_TAB_EN_US, "stranger", tz_index=0) is None


def test_out_of_range_tz_index_returns_none() -> None:
    """Negative or beyond-column-count tz_index returns None."""
    bundle = _build_bundle(["item_A"], np.array([[1.0, 1.0, 1.0, 1.0]], dtype=np.float32))
    backend = _make_backend()
    backend._fetch_callback(bundle, surface_id=SurfaceId.NEW_TAB_EN_US)

    assert backend.get_ratio(SurfaceId.NEW_TAB_EN_US, "item_A", tz_index=-1) is None
    assert backend.get_ratio(SurfaceId.NEW_TAB_EN_US, "item_A", tz_index=4) is None
    assert backend.get_ratio(SurfaceId.NEW_TAB_EN_US, "item_A", tz_index=99) is None


def test_get_ratio_when_invalid_surface_returns_none() -> None:
    """If the surface has no bundle loaded, get_ratio short-circuits to None."""
    backend = _make_backend()
    # No _fetch_callback fired yet.
    assert backend.is_valid(SurfaceId.NEW_TAB_EN_US) is False
    assert backend.get_ratio(SurfaceId.NEW_TAB_EN_US, "anything", tz_index=0) is None


# -----------------------------------------------------------------------------
# Validation failures preserve existing state
# -----------------------------------------------------------------------------
def test_schema_version_mismatch_preserves_state() -> None:
    """A bundle with a wrong schema_version is rejected without touching existing state."""
    # Land a good bundle first.
    good = _build_bundle(["item_A"], np.array([[1.5, 0.6, 1.0, 1.0]], dtype=np.float32))
    backend = _make_backend()
    backend._fetch_callback(good, surface_id=SurfaceId.NEW_TAB_EN_US)
    assert backend.is_valid(SurfaceId.NEW_TAB_EN_US) is True

    # Now hand it a bad version — old state should remain in place.
    bad = _build_bundle(
        ["item_B"],
        np.array([[0.0, 0.0, 0.0, 0.0]], dtype=np.float32),
        schema_version="tz_ratios_v2_future",
    )
    backend._fetch_callback(bad, surface_id=SurfaceId.NEW_TAB_EN_US)
    # is_valid still True; the original item_A is still findable; item_B is not.
    assert backend.is_valid(SurfaceId.NEW_TAB_EN_US) is True
    assert backend.get_ratio(SurfaceId.NEW_TAB_EN_US, "item_A", tz_index=0) == pytest.approx(1.5)
    assert backend.get_ratio(SurfaceId.NEW_TAB_EN_US, "item_B", tz_index=0) is None


def test_corrupt_data_preserves_state(caplog) -> None:
    """Garbage bytes are caught by the parser; existing state is preserved."""
    good = _build_bundle(["item_A"], np.array([[1.1, 0.9, 1.0, 1.0]], dtype=np.float32))
    backend = _make_backend()
    backend._fetch_callback(good, surface_id=SurfaceId.NEW_TAB_EN_US)
    assert backend.is_valid(SurfaceId.NEW_TAB_EN_US) is True

    backend._fetch_callback(b"not_a_safetensors_blob", surface_id=SurfaceId.NEW_TAB_EN_US)

    assert backend.is_valid(SurfaceId.NEW_TAB_EN_US) is True
    assert backend.get_ratio(SurfaceId.NEW_TAB_EN_US, "item_A", tz_index=0) == pytest.approx(1.1)
    assert any("failed to parse bundle" in r.message for r in caplog.records)


# -----------------------------------------------------------------------------
# Safety: clipping on load
# -----------------------------------------------------------------------------
def test_clips_ratios_outside_safe_band() -> None:
    """Ratios outside SAFE_RATIO_LOW / HIGH are clipped on load."""
    item_ids = ["bad"]
    ratios = np.array([[10.0, 0.01, SAFE_RATIO_HIGH, SAFE_RATIO_LOW]], dtype=np.float32)
    bundle = _build_bundle(item_ids, ratios)
    backend = _make_backend()
    backend._fetch_callback(bundle, surface_id=SurfaceId.NEW_TAB_EN_US)

    # Column 0 was 10.0, column 1 was 0.01 — both clipped.
    assert backend.get_ratio(SurfaceId.NEW_TAB_EN_US, "bad", tz_index=0) == pytest.approx(
        SAFE_RATIO_HIGH
    )
    assert backend.get_ratio(SurfaceId.NEW_TAB_EN_US, "bad", tz_index=1) == pytest.approx(
        SAFE_RATIO_LOW
    )


# -----------------------------------------------------------------------------
# Freshness
# -----------------------------------------------------------------------------
def test_is_valid_false_after_validity_period() -> None:
    """Once cache_time is older than VALIDITY_PERIOD_MINUTES, is_valid flips to False."""
    # Stamp the bundle's epoch_id as VALIDITY_PERIOD_MINUTES+1 minutes ago.
    stale_dt = datetime.now(timezone.utc) - timedelta(minutes=VALIDITY_PERIOD_MINUTES + 1)
    epoch_id = stale_dt.strftime("%Y%m%d-%H%M")
    bundle = _build_bundle(
        ["item_A"], np.array([[1.0, 1.0, 1.0, 1.0]], dtype=np.float32), epoch_id=epoch_id
    )
    backend = _make_backend()
    backend._fetch_callback(bundle, surface_id=SurfaceId.NEW_TAB_EN_US)

    assert backend.is_valid(SurfaceId.NEW_TAB_EN_US) is False
    # get_ratio returns None when invalid, regardless of item knowledge.
    assert backend.get_ratio(SurfaceId.NEW_TAB_EN_US, "item_A", tz_index=0) is None


# -----------------------------------------------------------------------------
# Empty stub
# -----------------------------------------------------------------------------
def test_empty_stub_always_invalid() -> None:
    """EmptyTZFeatureBackend reports invalid + returns None for every lookup."""
    backend = EmptyTZFeatureBackend()
    assert backend.is_valid(SurfaceId.NEW_TAB_EN_US) is False
    assert backend.get_ratio(SurfaceId.NEW_TAB_EN_US, "any", tz_index=0) is None
    assert backend.get_epoch_id(SurfaceId.NEW_TAB_EN_US) is None
    assert backend.update_count == 0


# -----------------------------------------------------------------------------
# Validation branches that don't have happy-path coverage above.
# -----------------------------------------------------------------------------
def _build_raw_bundle(
    ratios: np.ndarray,
    item_ids: list[str] | None = None,
    tz_labels: list[str] | None = None,
    baseline_tz: str = "ET",
    schema_version: str = SCHEMA_VERSION,
    epoch_id: str | None = None,
) -> bytes:
    """Bundle builder that lets tests inject malformed shapes/dtypes."""
    if item_ids is None:
        item_ids = [f"item_{i}" for i in range(ratios.shape[0])] if ratios.ndim >= 1 else []
    if tz_labels is None:
        tz_labels = ["PT", "MT", "CT", "ET"]
    if epoch_id is None:
        epoch_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    metadata = {
        "schema_version": schema_version,
        "epoch_id": epoch_id,
        "locale": "EN_US",
        "surface_id": "NEW_TAB_EN_US",
        "inferred_model_id": "inferred-v3-model",
        "tz_labels": json.dumps(tz_labels),
        "baseline_tz": baseline_tz,
        "non_baseline_tzs": json.dumps([t for t in tz_labels if t != baseline_tz]),
        "ratio_clip_low": "0.5",
        "ratio_clip_high": "2.0",
        "n_items": str(len(item_ids)),
        "item_to_idx": json.dumps({iid: i for i, iid in enumerate(item_ids)}),
        "model_epoch_id": "20260101-0000",
    }
    return save({"ratios": ratios}, metadata=metadata)


def test_dtype_mismatch_preserves_state(caplog) -> None:
    """Non-float32 ratios get rejected; existing state stays."""
    good = _build_bundle(["item_A"], np.array([[1.1, 0.9, 1.0, 1.0]], dtype=np.float32))
    backend = _make_backend()
    backend._fetch_callback(good, surface_id=SurfaceId.NEW_TAB_EN_US)

    bad = _build_raw_bundle(np.array([[1.0, 1.0, 1.0, 1.0]], dtype=np.float64))
    backend._fetch_callback(bad, surface_id=SurfaceId.NEW_TAB_EN_US)
    assert backend.get_ratio(SurfaceId.NEW_TAB_EN_US, "item_A", tz_index=0) == pytest.approx(1.1)
    assert any("dtype mismatch" in r.message for r in caplog.records)


def test_ndim_mismatch_preserves_state(caplog) -> None:
    """1D ratios tensor is rejected."""
    good = _build_bundle(["item_A"], np.array([[1.1, 0.9, 1.0, 1.0]], dtype=np.float32))
    backend = _make_backend()
    backend._fetch_callback(good, surface_id=SurfaceId.NEW_TAB_EN_US)

    bad = _build_raw_bundle(np.array([1.0, 1.0, 1.0, 1.0], dtype=np.float32), item_ids=["x"])
    backend._fetch_callback(bad, surface_id=SurfaceId.NEW_TAB_EN_US)
    assert any("must be 2D" in r.message for r in caplog.records)


def test_column_count_mismatch_preserves_state(caplog) -> None:
    """ratios.shape[1] must match len(tz_labels)."""
    good = _build_bundle(["item_A"], np.array([[1.1, 0.9, 1.0, 1.0]], dtype=np.float32))
    backend = _make_backend()
    backend._fetch_callback(good, surface_id=SurfaceId.NEW_TAB_EN_US)

    # ratios has 3 cols, tz_labels has 4 → mismatch.
    bad = _build_raw_bundle(
        np.array([[1.0, 1.0, 1.0]], dtype=np.float32),
        tz_labels=["PT", "MT", "CT", "ET"],
    )
    backend._fetch_callback(bad, surface_id=SurfaceId.NEW_TAB_EN_US)
    assert any("column count" in r.message for r in caplog.records)


def test_baseline_not_in_tz_labels_preserves_state(caplog) -> None:
    """baseline_tz must be one of tz_labels."""
    good = _build_bundle(["item_A"], np.array([[1.1, 0.9, 1.0, 1.0]], dtype=np.float32))
    backend = _make_backend()
    backend._fetch_callback(good, surface_id=SurfaceId.NEW_TAB_EN_US)

    bad = _build_raw_bundle(
        np.array([[1.0, 1.0, 1.0, 1.0]], dtype=np.float32),
        tz_labels=["PT", "MT", "CT", "ET"],
        baseline_tz="GMT",  # not in tz_labels
    )
    backend._fetch_callback(bad, surface_id=SurfaceId.NEW_TAB_EN_US)
    assert any("baseline_tz" in r.message for r in caplog.records)


def test_item_to_idx_size_mismatch_preserves_state(caplog) -> None:
    """item_to_idx entry count must match ratios row count."""
    good = _build_bundle(["item_A"], np.array([[1.1, 0.9, 1.0, 1.0]], dtype=np.float32))
    backend = _make_backend()
    backend._fetch_callback(good, surface_id=SurfaceId.NEW_TAB_EN_US)

    # 1 row of ratios, but item_to_idx claims 3 items.
    bad = _build_raw_bundle(
        np.array([[1.0, 1.0, 1.0, 1.0]], dtype=np.float32),
        item_ids=["a", "b", "c"],
    )
    backend._fetch_callback(bad, surface_id=SurfaceId.NEW_TAB_EN_US)
    assert any("item_to_idx size" in r.message for r in caplog.records)


def test_unparseable_epoch_id_treated_as_stale() -> None:
    """If epoch_id can't be parsed, the bundle loads but is_valid returns False."""
    bundle = _build_raw_bundle(
        np.array([[1.0, 1.0, 1.0, 1.0]], dtype=np.float32),
        item_ids=["item_A"],
        epoch_id="not-a-date",
    )
    backend = _make_backend()
    backend._fetch_callback(bundle, surface_id=SurfaceId.NEW_TAB_EN_US)
    assert backend.is_valid(SurfaceId.NEW_TAB_EN_US) is False
    # Recorded epoch_id is still the raw string for diagnostics.
    assert backend.get_epoch_id(SurfaceId.NEW_TAB_EN_US) == "not-a-date"


def test_get_epoch_id_returns_loaded_epoch() -> None:
    """get_epoch_id returns the bundle's epoch_id after a successful load."""
    epoch = "20260603-1200"
    bundle = _build_bundle(
        ["item_A"],
        np.array([[1.1, 0.9, 1.0, 1.0]], dtype=np.float32),
        epoch_id=epoch,
    )
    backend = _make_backend()
    backend._fetch_callback(bundle, surface_id=SurfaceId.NEW_TAB_EN_US)
    assert backend.get_epoch_id(SurfaceId.NEW_TAB_EN_US) == epoch


def test_update_count_sums_across_surfaces() -> None:
    """update_count returns the sum of each synced blob's update_count."""

    class _StubBlob:
        def __init__(self, count: int) -> None:
            self._count = count

        def set_fetch_binary_callback(self, cb) -> None:
            pass

        @property
        def update_count(self) -> int:
            return self._count

    backend = TZFeatureBackend(
        synced_gcs_blobs={SurfaceId.NEW_TAB_EN_US: _StubBlob(7)}  # type: ignore[dict-item]
    )
    assert backend.update_count == 7
