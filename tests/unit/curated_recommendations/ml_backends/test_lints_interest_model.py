"""Unit tests for the LinTS-interest backend.

Builds a synthetic v4 safetensors bundle in-memory (same byte layout the
ml-services inference flow produces), feeds it through ``_fetch_callback``,
and verifies:

  - happy-path load + scoring
  - schema/format mismatch → existing state preserved, surface treated as
    invalid for future requests
  - corrupt tensors → same fallback
  - per-request scoring matches the reference dense + ``solve_triangular``
    path bit-for-bit (within float32 ulps)
  - unknown items get bias + topic_main only (cold-start escape hatch)
  - cache time expiry triggers ``is_valid`` → False
  - empty-stub backend always reports invalid
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import numpy as np
import pytest
from safetensors.numpy import save
from scipy.linalg import solve_triangular

from merino.curated_recommendations.corpus_backends.protocol import SurfaceId
from merino.curated_recommendations.ml_backends.lints_interest_model import (
    EmptyLinTSInterestBackend,
    LinTSInterestBackend,
    L_FORMAT_LAPACK_LOWER_PACKED,
    SCHEMA_VERSION,
    VALIDITY_PERIOD_MINUTES,
)


# -----------------------------------------------------------------------------
# Bundle builder — mirrors ml-services' serialize_and_upload byte-for-byte.
# -----------------------------------------------------------------------------
def _pack_lower_lapack(L_dense: np.ndarray) -> np.ndarray:
    """Dense lower-triangular → LAPACK column-major lower-packed (the v4 layout)."""
    d = L_dense.shape[0]
    out = np.empty(d * (d + 1) // 2, dtype=L_dense.dtype)
    offset = 0
    for j in range(d):
        n_col = d - j
        out[offset : offset + n_col] = L_dense[j:, j]
        offset += n_col
    return out


def _build_synthetic_bundle(
    n_items: int = 10,
    n_topics: int = 7,
    schema_version: str = SCHEMA_VERSION,
    l_format: str = L_FORMAT_LAPACK_LOWER_PACKED,
    epoch_id: str | None = None,
    v_value: float = 0.005,
    corrupt_dim: bool = False,
    corrupt_dtype: bool = False,
    l_as_float16: bool = False,
) -> tuple[bytes, dict]:
    """Assemble a v4 bundle from a tiny synthetic model and return (bytes, expected).

    ``expected`` carries the dense L, theta_hat, and index dicts so tests can
    check round-trip correctness without re-deriving them.
    """
    rng = np.random.default_rng(0)
    bias_idx = 0
    # Index layout: bias=0, topic_main=1..n_topics, item_main=next, item_topic=last.
    topic_main_to_idx = {t: 1 + t for t in range(n_topics)}

    item_to_idx: dict[str, int] = {}
    item_topic_to_idx: dict[tuple[str, int], int] = {}
    next_idx = 1 + n_topics
    for i in range(n_items):
        iid = f"item_{i:02d}"
        item_to_idx[iid] = next_idx
        next_idx += 1
    # Pair every item with the first three topics so we have realistic coverage
    # without blowing up the dim.
    for i in range(n_items):
        iid = f"item_{i:02d}"
        for t in range(min(3, n_topics)):
            item_topic_to_idx[(iid, t)] = next_idx
            next_idx += 1
    d = next_idx

    # Build a real PSD A and Cholesky-factor it so L is a true Cholesky factor.
    M = rng.standard_normal((d, d)).astype(np.float32)
    A = (M @ M.T).astype(np.float32) + (d * np.eye(d, dtype=np.float32))
    L_dense = np.linalg.cholesky(A).astype(np.float32)
    theta_hat = rng.standard_normal(d).astype(np.float32) * np.float32(0.001)

    L_packed = _pack_lower_lapack(L_dense)
    if corrupt_dim:
        # Drop one entry so reshape verification fails downstream.
        L_packed = L_packed[:-1]
    if corrupt_dtype:
        L_packed = L_packed.astype(np.float64)
    if l_as_float16:
        # Mirrors the inference flow's storage cast — merino must upconvert
        # to float32 on load (since BLAS stpsv has no float16 variant).
        L_packed = L_packed.astype(np.float16)

    metadata: dict[str, str] = {
        "schema_version": schema_version,
        "model_id": "inferred-v3-model",
        "epoch_id": epoch_id or datetime.now(timezone.utc).strftime("%Y%m%d-%H%M"),
        "dim": str(d),
        "v": str(v_value),
        "n_topics": str(n_topics),
        "topic_names": json.dumps([f"topic_{t}" for t in range(n_topics)]),
        "thresholds": json.dumps([[0.25, 0.46, 0.8]] * n_topics),
        "bias_idx": str(bias_idx),
        "L_format": l_format,
        "topic_main_to_idx": json.dumps({str(t): idx for t, idx in topic_main_to_idx.items()}),
        "item_to_idx": json.dumps(item_to_idx),
        "item_topic_to_idx": json.dumps(
            {f"{iid}|{t}": idx for (iid, t), idx in item_topic_to_idx.items()}
        ),
    }
    blob = save({"L_lower": L_packed, "theta_hat": theta_hat}, metadata=metadata)

    return blob, {
        "d": d,
        "n_topics": n_topics,
        "L_dense": L_dense,
        "theta_hat": theta_hat,
        "bias_idx": bias_idx,
        "v": v_value,
        "topic_main_to_idx": topic_main_to_idx,
        "item_to_idx": item_to_idx,
        "item_topic_to_idx": item_topic_to_idx,
    }


def _make_backend(synced_blob_mock: MagicMock | None = None) -> LinTSInterestBackend:
    """Build a backend with a stand-in SyncedGcsBlob; tests drive ``_fetch_callback`` directly."""
    blob = synced_blob_mock or MagicMock()
    return LinTSInterestBackend(synced_gcs_blobs={SurfaceId.NEW_TAB_EN_US: blob})


# -----------------------------------------------------------------------------
# Happy path — loading a well-formed v4 bundle populates per-surface state.
# -----------------------------------------------------------------------------
def test_is_valid_after_fresh_load() -> None:
    """A fresh-epoch bundle marks the surface as valid."""
    blob, expected = _build_synthetic_bundle()
    backend = _make_backend()
    backend._fetch_callback(blob, surface_id=SurfaceId.NEW_TAB_EN_US)

    assert backend.is_valid(SurfaceId.NEW_TAB_EN_US)
    assert backend._dim[SurfaceId.NEW_TAB_EN_US] == expected["d"]


def test_metadata_round_trips() -> None:
    """All metadata index dicts and scalars are restored from the safetensors header."""
    blob, expected = _build_synthetic_bundle()
    backend = _make_backend()
    backend._fetch_callback(blob, surface_id=SurfaceId.NEW_TAB_EN_US)

    assert backend._item_to_idx[SurfaceId.NEW_TAB_EN_US] == expected["item_to_idx"]
    assert backend._topic_main_to_idx[SurfaceId.NEW_TAB_EN_US] == expected["topic_main_to_idx"]
    assert backend._item_topic_to_idx[SurfaceId.NEW_TAB_EN_US] == expected["item_topic_to_idx"]
    assert backend._bias_idx[SurfaceId.NEW_TAB_EN_US] == expected["bias_idx"]
    assert backend._v[SurfaceId.NEW_TAB_EN_US] == pytest.approx(expected["v"])


def test_has_item_returns_true_for_known() -> None:
    """Items present in item_to_idx report True; unknown items report False."""
    blob, expected = _build_synthetic_bundle()
    backend = _make_backend()
    backend._fetch_callback(blob, surface_id=SurfaceId.NEW_TAB_EN_US)

    known = next(iter(expected["item_to_idx"]))
    assert backend.has_item(SurfaceId.NEW_TAB_EN_US, known)
    assert not backend.has_item(SurfaceId.NEW_TAB_EN_US, "no_such_item")


# -----------------------------------------------------------------------------
# Validation failures — bad bundles must NOT clobber existing state.
# -----------------------------------------------------------------------------
def test_schema_version_mismatch_keeps_state_unset() -> None:
    """A bundle with the wrong schema_version is rejected; state stays empty."""
    bad_blob, _ = _build_synthetic_bundle(schema_version="lints_interest_v3")
    backend = _make_backend()
    backend._fetch_callback(bad_blob, surface_id=SurfaceId.NEW_TAB_EN_US)

    assert not backend.is_valid(SurfaceId.NEW_TAB_EN_US)
    assert SurfaceId.NEW_TAB_EN_US not in backend._dim


def test_l_format_mismatch_keeps_state_unset() -> None:
    """A bundle with the wrong L_format is rejected; state stays empty."""
    bad_blob, _ = _build_synthetic_bundle(l_format="lower_triangular_flat")
    backend = _make_backend()
    backend._fetch_callback(bad_blob, surface_id=SurfaceId.NEW_TAB_EN_US)

    assert not backend.is_valid(SurfaceId.NEW_TAB_EN_US)


def test_dim_mismatch_keeps_state_unset() -> None:
    """A bundle whose L_lower length does not match d·(d+1)/2 is rejected."""
    bad_blob, _ = _build_synthetic_bundle(corrupt_dim=True)
    backend = _make_backend()
    backend._fetch_callback(bad_blob, surface_id=SurfaceId.NEW_TAB_EN_US)

    assert not backend.is_valid(SurfaceId.NEW_TAB_EN_US)


def test_dtype_mismatch_keeps_state_unset() -> None:
    """A bundle whose tensors aren't float32 is rejected."""
    bad_blob, _ = _build_synthetic_bundle(corrupt_dtype=True)
    backend = _make_backend()
    backend._fetch_callback(bad_blob, surface_id=SurfaceId.NEW_TAB_EN_US)

    assert not backend.is_valid(SurfaceId.NEW_TAB_EN_US)


def test_float16_l_lower_upconverts_on_load() -> None:
    """A bundle with float16 L_lower (the inference flow's storage format)
    loads cleanly — the loader upconverts to float32 before validation.
    """
    blob, expected = _build_synthetic_bundle(l_as_float16=True)
    backend = _make_backend()
    backend._fetch_callback(blob, surface_id=SurfaceId.NEW_TAB_EN_US)

    assert backend.is_valid(SurfaceId.NEW_TAB_EN_US)
    # After load, the in-memory L is float32 (BLAS stpsv requirement).
    assert backend._L_packed[SurfaceId.NEW_TAB_EN_US].dtype == np.float32
    # Sanity: a score request runs without raising.
    rng = np.random.default_rng(0)
    scores = backend.score_request(
        SurfaceId.NEW_TAB_EN_US,
        strengths={f"topic_{t}": 0.5 for t in range(3)},
        candidate_item_ids=list(expected["item_to_idx"].keys())[:5],
        rng=rng,
    )
    assert scores.shape == (5,)
    assert np.all(np.isfinite(scores))


def test_bad_bundle_does_not_clobber_existing_good_state() -> None:
    """A failing reload keeps the previously-loaded valid state intact."""
    good_blob, _ = _build_synthetic_bundle()
    bad_blob, _ = _build_synthetic_bundle(schema_version="lints_interest_v999")
    backend = _make_backend()

    backend._fetch_callback(good_blob, surface_id=SurfaceId.NEW_TAB_EN_US)
    good_dim = backend._dim[SurfaceId.NEW_TAB_EN_US]

    backend._fetch_callback(bad_blob, surface_id=SurfaceId.NEW_TAB_EN_US)
    assert backend.is_valid(SurfaceId.NEW_TAB_EN_US)
    assert backend._dim[SurfaceId.NEW_TAB_EN_US] == good_dim


# -----------------------------------------------------------------------------
# Scoring correctness — packed `stpsv` must match dense `solve_triangular`.
# -----------------------------------------------------------------------------
def test_score_matches_reference_implementation() -> None:
    """Per-item scores match a dense ``solve_triangular`` reference within float32 ulps."""
    blob, expected = _build_synthetic_bundle(n_topics=7, n_items=10)
    backend = _make_backend()
    backend._fetch_callback(blob, surface_id=SurfaceId.NEW_TAB_EN_US)

    items = list(expected["item_to_idx"].keys())
    strengths = {f"topic_{t}": (0.5 if t < 3 else 0.0) for t in range(7)}

    # Reference: reconstruct dense L, run solve_triangular with the SAME ε
    # the backend will draw, then score every item by the score formula in
    # the v4 schema.
    rng_for_backend = np.random.default_rng(42)
    rng_for_reference = np.random.default_rng(42)

    scores = backend.score_request(SurfaceId.NEW_TAB_EN_US, strengths, items, rng_for_backend)

    d = expected["d"]
    L_dense = expected["L_dense"]
    theta_hat = expected["theta_hat"]
    v_val = expected["v"]
    eps = rng_for_reference.standard_normal(d).astype(np.float32)
    z = solve_triangular(L_dense.T, eps, lower=False, check_finite=False)
    theta_tilde = theta_hat + np.float32(v_val) * z

    for i, iid in enumerate(items):
        ref = float(theta_tilde[expected["bias_idx"]])
        ref += float(theta_tilde[expected["item_to_idx"][iid]])
        for t in range(7):
            s = strengths[f"topic_{t}"]
            if s == 0.0:
                continue
            ref += s * float(theta_tilde[expected["topic_main_to_idx"][t]])
            pair_idx = expected["item_topic_to_idx"].get((iid, t))
            if pair_idx is not None:
                ref += s * float(theta_tilde[pair_idx])
        assert float(scores[i]) == pytest.approx(ref, rel=1e-4, abs=1e-5), (
            f"score mismatch for {iid}: backend={scores[i]} ref={ref}"
        )


def test_unknown_item_gets_bias_plus_topic_main_only() -> None:
    """Items not in item_to_idx get only the bias + topic_main contributions."""
    blob, expected = _build_synthetic_bundle(n_topics=7, n_items=5)
    backend = _make_backend()
    backend._fetch_callback(blob, surface_id=SurfaceId.NEW_TAB_EN_US)

    # Use the same rng for both calls so the θ̃ draw is identical.
    strengths = {f"topic_{t}": (0.5 if t < 3 else 0.0) for t in range(7)}
    rng_known = np.random.default_rng(7)
    rng_unknown = np.random.default_rng(7)

    score_unknown = backend.score_request(
        SurfaceId.NEW_TAB_EN_US, strengths, ["NEVER_SEEN"], rng_unknown
    )
    # The unknown item should score = bias + Σ_t strength_t · θ̃[topic_main(t)],
    # i.e. no per-item terms. Verify by computing the reference manually.
    d = expected["d"]
    L_dense = expected["L_dense"]
    theta_hat = expected["theta_hat"]
    v_val = expected["v"]
    eps = rng_known.standard_normal(d).astype(np.float32)
    z = solve_triangular(L_dense.T, eps, lower=False, check_finite=False)
    theta_tilde = theta_hat + np.float32(v_val) * z
    ref = float(theta_tilde[expected["bias_idx"]])
    for t in range(7):
        s = strengths[f"topic_{t}"]
        if s == 0.0:
            continue
        ref += s * float(theta_tilde[expected["topic_main_to_idx"][t]])

    assert float(score_unknown[0]) == pytest.approx(ref, rel=1e-4, abs=1e-5)


def test_score_request_raises_on_invalid_surface() -> None:
    """Scoring against a surface with no loaded state raises RuntimeError."""
    backend = _make_backend()  # no bundle ever loaded
    with pytest.raises(RuntimeError):
        backend.score_request(
            SurfaceId.NEW_TAB_EN_US,
            {"topic_0": 0.5},
            ["x"],
            np.random.default_rng(0),
        )


# -----------------------------------------------------------------------------
# Freshness expiry — bundles older than VALIDITY_PERIOD_MINUTES become invalid.
# -----------------------------------------------------------------------------
def test_stale_bundle_is_invalid() -> None:
    """A bundle older than VALIDITY_PERIOD_MINUTES makes the surface invalid."""
    # epoch_id far in the past → cache_time well outside the freshness window.
    stale_epoch = (
        datetime.now(timezone.utc) - timedelta(minutes=VALIDITY_PERIOD_MINUTES + 30)
    ).strftime("%Y%m%d-%H%M")
    blob, _ = _build_synthetic_bundle(epoch_id=stale_epoch)
    backend = _make_backend()
    backend._fetch_callback(blob, surface_id=SurfaceId.NEW_TAB_EN_US)

    assert not backend.is_valid(SurfaceId.NEW_TAB_EN_US)


def test_fresh_bundle_is_valid() -> None:
    """A bundle with a current epoch_id makes the surface valid."""
    blob, _ = _build_synthetic_bundle()  # epoch_id = now()
    backend = _make_backend()
    backend._fetch_callback(blob, surface_id=SurfaceId.NEW_TAB_EN_US)

    assert backend.is_valid(SurfaceId.NEW_TAB_EN_US)


# -----------------------------------------------------------------------------
# Empty stub — used when the kill switch is off; must always be invalid.
# -----------------------------------------------------------------------------
def test_empty_backend_always_invalid() -> None:
    """is_valid() returns False for every surface on the empty stub."""
    backend = EmptyLinTSInterestBackend()
    assert not backend.is_valid(SurfaceId.NEW_TAB_EN_US)
    assert not backend.is_valid(SurfaceId.NEW_TAB_EN_CA)


def test_empty_backend_score_request_raises() -> None:
    """score_request on the empty stub raises (caller must guard with is_valid)."""
    backend = EmptyLinTSInterestBackend()
    with pytest.raises(RuntimeError):
        backend.score_request(
            SurfaceId.NEW_TAB_EN_US,
            {},
            ["x"],
            np.random.default_rng(0),
        )


def test_empty_backend_has_item_always_false() -> None:
    """has_item() always returns False on the empty stub."""
    backend = EmptyLinTSInterestBackend()
    assert not backend.has_item(SurfaceId.NEW_TAB_EN_US, "anything")


def test_empty_backend_update_count_zero() -> None:
    """update_count is 0 since the empty stub has no SyncedGcsBlobs."""
    backend = EmptyLinTSInterestBackend()
    assert backend.update_count == 0
