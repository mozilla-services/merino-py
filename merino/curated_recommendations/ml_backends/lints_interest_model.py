"""Backend for the ContextualLinTSInterest ranker.

Loads the per-surface safetensors bundle published by ml-services'
``ContextualLinTSInterestInferenceFlow`` and exposes a per-request scoring
method that samples θ̃ from the model's posterior and scores candidate items
in one vectorized pass.

Per-surface design mirrors ``gcs_ml_recs.GcsMLRecs``: one ``SyncedGcsBlob``
per ``SurfaceId``, atomically-installed state behind ``is_valid(surface_id)``.
"""

from datetime import datetime, timedelta, timezone
from functools import partial
import json
import logging
import tempfile

import numpy as np
from safetensors import safe_open
from scipy.linalg.blas import stpsv

from merino.curated_recommendations.corpus_backends.protocol import SurfaceId, Topic
from merino.curated_recommendations.ml_backends.protocol import (
    TIME_ZONE_OFFSET_INFERRED_KEY,
)
from merino.utils.synced_gcs_blob import SyncedGcsBlob

logger = logging.getLogger(__name__)

# Bundle schema we accept. Mismatch is treated as "invalid" — the request
# falls through to the cohort path or vanilla TS.
SCHEMA_VERSION = "lints_interest_v4"
L_FORMAT_LAPACK_LOWER_PACKED = "lapack_lower_packed"

# How long after the bundle's epoch_id we still consider it fresh enough to
# serve. Matches `gcs_ml_recs.VALIDITY_PERIOD_MINUTES`.
VALIDITY_PERIOD_MINUTES = 60


class LinTSInterestBackend:
    """Per-surface backend that loads the LinTS-interest safetensors bundle and
    samples θ̃ per request via packed-triangular solve.
    """

    def __init__(self, synced_gcs_blobs: dict[SurfaceId, SyncedGcsBlob]) -> None:
        self.synced_blobs: dict[SurfaceId, SyncedGcsBlob] = synced_gcs_blobs

        # Per-surface state, all populated atomically inside ``_fetch_callback``.
        self._L_packed: dict[SurfaceId, np.ndarray] = {}
        self._theta_hat: dict[SurfaceId, np.ndarray] = {}
        self._item_to_idx: dict[SurfaceId, dict[str, int]] = {}
        self._item_topic_to_idx: dict[SurfaceId, dict[tuple[str, int], int]] = {}
        self._topic_main_to_idx: dict[SurfaceId, dict[int, int]] = {}
        self._topic_names: dict[SurfaceId, list[str]] = {}
        self._dim: dict[SurfaceId, int] = {}
        self._bias_idx: dict[SurfaceId, int] = {}
        self._v: dict[SurfaceId, float] = {}
        self._cache_time: dict[SurfaceId, datetime] = {}
        self._model_id: dict[SurfaceId, str] = {}
        self._epoch_id: dict[SurfaceId, str] = {}
        # Optional tz_pred feature state. -1 sentinel = "tz_pred not present
        # in this bundle, skip the adjustment entirely".
        self._tz_pred_idx: dict[SurfaceId, int] = {}
        self._tz_baseline_idx: dict[SurfaceId, int] = {}
        self._tz_preds: dict[SurfaceId, np.ndarray] = {}
        self._tz_pred_item_to_idx: dict[SurfaceId, dict[str, int]] = {}

        for surface_id, blob in self.synced_blobs.items():
            blob.set_fetch_binary_callback(partial(self._fetch_callback, surface_id=surface_id))

    # ----------------------------------------------------------------- load

    def _fetch_callback(self, data: bytes, surface_id: SurfaceId) -> None:
        """Parse a v4 safetensors bundle and atomically install per-surface state.

        Validation failures log + return without touching existing state, so a
        bad publish doesn't break a previously-working surface.
        """
        try:
            parsed = self._parse_bundle(data)
        except Exception as e:
            logger.error(f"LinTSInterestBackend: failed to parse bundle for {surface_id}: {e}")
            return

        # Atomic install: every field is set together so ``is_valid`` never sees
        # a partially-loaded state.
        self._L_packed[surface_id] = parsed["L_packed"]
        self._theta_hat[surface_id] = parsed["theta_hat"]
        self._item_to_idx[surface_id] = parsed["item_to_idx"]
        self._item_topic_to_idx[surface_id] = parsed["item_topic_to_idx"]
        self._topic_main_to_idx[surface_id] = parsed["topic_main_to_idx"]
        self._topic_names[surface_id] = parsed["topic_names"]
        self._dim[surface_id] = parsed["dim"]
        self._bias_idx[surface_id] = parsed["bias_idx"]
        self._v[surface_id] = parsed["v"]
        self._cache_time[surface_id] = parsed["cache_time"]
        self._model_id[surface_id] = parsed["model_id"]
        self._epoch_id[surface_id] = parsed["epoch_id"]
        self._tz_pred_idx[surface_id] = parsed["tz_pred_idx"]
        self._tz_baseline_idx[surface_id] = parsed["tz_baseline_idx"]
        self._tz_preds[surface_id] = parsed["tz_preds"]
        self._tz_pred_item_to_idx[surface_id] = parsed["tz_pred_item_to_idx"]

        logger.info(
            f"LinTSInterestBackend: loaded {surface_id} dim={parsed['dim']} "
            f"items={len(parsed['item_to_idx'])} epoch={parsed['epoch_id']}"
        )

    @staticmethod
    def _parse_bundle(data: bytes) -> dict:
        """Validate + parse a v4 bundle into a dict of fields.

        Raises if schema_version, L_format, or tensor shapes don't match
        expectations. Caller catches and treats it as "invalid bundle, keep
        existing state".
        """
        # safetensors' Python API takes a file path, so we land the bytes in a
        # tempfile. The file is auto-deleted when the with-block exits.
        with tempfile.NamedTemporaryFile(suffix=".safetensors") as tmp:
            tmp.write(data)
            tmp.flush()
            with safe_open(tmp.name, framework="numpy") as st:
                meta = st.metadata() or {}
                schema_version = meta.get("schema_version")
                if schema_version != SCHEMA_VERSION:
                    raise ValueError(
                        f"schema_version mismatch: got {schema_version!r}, "
                        f"expected {SCHEMA_VERSION!r}"
                    )
                l_format = meta.get("L_format")
                if l_format != L_FORMAT_LAPACK_LOWER_PACKED:
                    raise ValueError(
                        f"L_format mismatch: got {l_format!r}, "
                        f"expected {L_FORMAT_LAPACK_LOWER_PACKED!r}"
                    )

                dim = int(meta["dim"])
                bias_idx = int(meta["bias_idx"])
                v = float(meta["v"])

                L_packed = st.get_tensor("L_lower").copy()
                theta_hat = st.get_tensor("theta_hat").copy()
                tensor_keys = set(st.keys())
                tz_preds_tensor = (
                    st.get_tensor("tz_preds").copy() if "tz_preds" in tensor_keys else None
                )

        # ml-services serializes L as float16 to halve disk/wire size; we
        # upconvert to float32 here because scipy.linalg.blas.stpsv (used at
        # score time) has no float16 variant. float32 L_packed is kept
        # resident — the per-worker memory cost is the same as before the
        # float16 storage change, but downloads and GCS storage halve.
        # Validated in ml-services/bench_fp16_quick.py: top-K rankings are
        # bit-identical between float32 and float16-round-tripped scores.
        if L_packed.dtype == np.float16:
            L_packed = L_packed.astype(np.float32)
        # Tensor sanity: catches truncation and silent dtype drift.
        if L_packed.dtype != np.float32 or theta_hat.dtype != np.float32:
            raise ValueError(
                f"tensor dtype mismatch: L_lower={L_packed.dtype}, "
                f"theta_hat={theta_hat.dtype}; expected float32 "
                "(or float16 for L_lower with on-load upconversion)"
            )
        expected_l_size = dim * (dim + 1) // 2
        if L_packed.shape != (expected_l_size,):
            raise ValueError(
                f"L_lower shape {L_packed.shape} does not match d·(d+1)/2 = {expected_l_size}"
            )
        if theta_hat.shape != (dim,):
            raise ValueError(f"theta_hat shape {theta_hat.shape} does not match dim={dim}")

        # Index dicts. item_topic_to_idx uses pipe-delimited string keys on disk;
        # rebuild as (item_id, topic_idx) tuples for fast lookup at score time.
        item_to_idx = json.loads(meta["item_to_idx"])
        item_topic_to_idx_raw = json.loads(meta["item_topic_to_idx"])
        item_topic_to_idx: dict[tuple[str, int], int] = {}
        for k, v_idx in item_topic_to_idx_raw.items():
            iid, topic_str = k.split("|", 1)
            item_topic_to_idx[(iid, int(topic_str))] = int(v_idx)
        topic_main_to_idx = {
            int(k): int(v_idx) for k, v_idx in json.loads(meta["topic_main_to_idx"]).items()
        }
        topic_names = json.loads(meta["topic_names"])

        # Drift guard: the bundle's topic_names must match the strings that
        # merino's `decode_dp_interests` uses as keys in the strength dict
        valid_topic_values = {t.value for t in Topic}
        unknown_topic_names = [n for n in topic_names if n not in valid_topic_values]
        if unknown_topic_names:
            logger.warning(
                "LinTSInterestBackend: bundle topic_names contain entries not in "
                "the Topic enum — strength lookup will silently zero for these. "
                "Update ml-services' INTEREST_LOCALE_CONFIGS or merino's Topic enum. "
                f"unknown={unknown_topic_names} all_topic_names={topic_names}"
            )

        epoch_id = meta.get("epoch_id", "")
        try:
            cache_time = datetime.strptime(epoch_id, "%Y%m%d-%H%M").replace(tzinfo=timezone.utc)
        except ValueError:
            # Without a parsable epoch we can't enforce freshness, so treat
            # the bundle as already-stale by zeroing the cache time.
            cache_time = datetime.fromtimestamp(0, tz=timezone.utc)

        # Optional tz_pred feature pieces. Old bundles without the tz fields
        # land here with sentinel values that disable the adjustment entirely.
        tz_pred_idx = int(meta.get("tz_pred_idx", "-1"))
        tz_baseline_idx = int(meta.get("tz_baseline_idx", "-1"))
        tz_pred_item_to_idx: dict[str, int] = {
            str(k): int(val)
            for k, val in json.loads(meta.get("tz_pred_item_to_idx", "{}")).items()
        }
        if tz_preds_tensor is not None:
            if tz_preds_tensor.dtype != np.float32:
                tz_preds_tensor = tz_preds_tensor.astype(np.float32)
            if tz_preds_tensor.ndim != 2:
                raise ValueError(f"tz_preds must be 2D, got shape {tz_preds_tensor.shape}")
            if len(tz_pred_item_to_idx) != tz_preds_tensor.shape[0]:
                raise ValueError(
                    f"tz_pred_item_to_idx size {len(tz_pred_item_to_idx)} "
                    f"does not match tz_preds row count {tz_preds_tensor.shape[0]}"
                )
        else:
            tz_preds_tensor = np.zeros((0, 0), dtype=np.float32)

        return {
            "L_packed": L_packed,
            "theta_hat": theta_hat,
            "item_to_idx": item_to_idx,
            "item_topic_to_idx": item_topic_to_idx,
            "topic_main_to_idx": topic_main_to_idx,
            "topic_names": topic_names,
            "dim": dim,
            "bias_idx": bias_idx,
            "v": v,
            "cache_time": cache_time,
            "model_id": meta.get("model_id", "unknown"),
            "epoch_id": epoch_id,
            "tz_pred_idx": tz_pred_idx,
            "tz_baseline_idx": tz_baseline_idx,
            "tz_preds": tz_preds_tensor,
            "tz_pred_item_to_idx": tz_pred_item_to_idx,
        }

    # ----------------------------------------------------------------- query

    def is_valid(self, surface_id: SurfaceId) -> bool:
        """Return whether this surface has a fresh, well-formed bundle loaded."""
        cache_time = self._cache_time.get(surface_id)
        dim = self._dim.get(surface_id)
        if cache_time is None or not dim:
            return False
        return datetime.now(timezone.utc) - cache_time <= timedelta(
            minutes=VALIDITY_PERIOD_MINUTES
        )

    def score_request(
        self,
        surface_id: SurfaceId,
        strengths: dict[str, float],
        candidate_item_ids: list[str],
        rng: np.random.Generator,
    ) -> np.ndarray:
        """Sample θ̃ once, then score every candidate against it.

        Items not in ``item_to_idx`` for this surface get ``bias + topic_main``
        contributions only (no ``item_main`` term, no per-item ``(item × topic)``
        terms). The caller is responsible for falling back to vanilla TS if it
        wants those items explored aggressively.

        :returns: float32 array aligned to ``candidate_item_ids``.
        """
        if not self.is_valid(surface_id):
            raise RuntimeError(
                f"LinTSInterestBackend.score_request called for {surface_id} "
                f"without a valid bundle"
            )
        d = self._dim[surface_id]
        bias_idx = self._bias_idx[surface_id]
        v = self._v[surface_id]
        L_packed = self._L_packed[surface_id]
        theta_hat = self._theta_hat[surface_id]
        item_to_idx = self._item_to_idx[surface_id]
        item_topic_to_idx = self._item_topic_to_idx[surface_id]
        topic_main_to_idx = self._topic_main_to_idx[surface_id]
        topic_names = self._topic_names[surface_id]
        n_topics = len(topic_names)
        tz_pred_idx = self._tz_pred_idx.get(surface_id, -1)
        tz_baseline_idx = self._tz_baseline_idx.get(surface_id, -1)
        tz_preds = self._tz_preds.get(surface_id, np.zeros((0, 0), dtype=np.float32))
        tz_pred_item_to_idx = self._tz_pred_item_to_idx.get(surface_id, {})

        # 1) Sample θ̃ = θ̂ + v · L^{-T} ε via the packed triangular solve.
        eps = rng.standard_normal(d).astype(np.float32)
        x = stpsv(d, L_packed, eps, lower=1, trans=1, diag=0, overwrite_x=1)
        theta_tilde = theta_hat + np.float32(v) * x

        # 2) Constant-across-candidates terms: bias + Σ_t strength_t · θ̃[topic_main(t)]
        strength_vec = np.zeros(n_topics, dtype=np.float32)
        for t, name in enumerate(topic_names):
            sv = strengths.get(name)
            if isinstance(sv, (int, float)):
                strength_vec[t] = float(sv)
        topic_main_indices = np.array(
            [topic_main_to_idx[t] for t in range(n_topics)], dtype=np.int64
        )
        const_score = float(theta_tilde[bias_idx]) + float(
            np.dot(strength_vec, theta_tilde[topic_main_indices])
        )

        # Resolve the user's tz_index once. tz_pred_idx >= 0 indicates the
        # bundle carries the feature. Baseline-TZ users (e.g. ET) get no
        # adjustment because there's no published ratio for the baseline.
        tz_pred_active = False
        user_tz_idx = -1
        tz_pred_coef = 0.0
        if tz_pred_idx >= 0 and tz_preds is not None and tz_preds.size > 0:
            raw_tz = strengths.get(TIME_ZONE_OFFSET_INFERRED_KEY)
            if isinstance(raw_tz, (int, float)):
                user_tz_idx = int(raw_tz)
                if 0 <= user_tz_idx < tz_preds.shape[1] and user_tz_idx != tz_baseline_idx:
                    tz_pred_active = True
                    tz_pred_coef = float(theta_tilde[tz_pred_idx])

        # 3) Per-candidate: item_main if known, plus active (item × topic) pairs,
        # plus the tz_pred contribution when the bundle exposes it.
        scores = np.full(len(candidate_item_ids), const_score, dtype=np.float32)
        for r, raw_iid in enumerate(candidate_item_ids):
            iid = str(raw_iid)
            ii = item_to_idx.get(iid)
            if ii is not None:
                scores[r] += theta_tilde[ii]
            for t in range(n_topics):
                sv_t = strength_vec[t]
                if sv_t == 0.0:
                    continue
                pi = item_topic_to_idx.get((iid, t))
                if pi is not None:
                    scores[r] += sv_t * theta_tilde[pi]
            if tz_pred_active:
                pred_row = tz_pred_item_to_idx.get(iid)
                if pred_row is not None:
                    scores[r] += tz_pred_coef * float(tz_preds[pred_row, user_tz_idx])
        return scores

    def has_item(self, surface_id: SurfaceId, corpus_item_id: str) -> bool:
        """Return whether the surface's model knows this item.

        Useful for callers that want to fall back to vanilla TS for the
        unknown-item portion of the candidate set.
        """
        items = self._item_to_idx.get(surface_id)
        if items is None:
            return False
        return str(corpus_item_id) in items

    def get_model_id(self, surface_id: SurfaceId) -> str | None:
        """Return the inferred-interests model id this surface was trained on."""
        return self._model_id.get(surface_id)

    @property
    def update_count(self) -> int:
        """Total bundle refresh count across all surfaces (for metrics)."""
        return sum(blob.update_count for blob in self.synced_blobs.values())


class EmptyLinTSInterestBackend:
    """No-op backend used when the kill switch is off or GCS init fails.

    Always reports ``is_valid() == False`` so the request flow naturally falls
    through to the cohort or vanilla TS ranker.
    """

    def __init__(self) -> None:
        pass

    def is_valid(self, surface_id: SurfaceId) -> bool:
        """Return False so the caller falls back to the next-tier ranker."""
        return False

    def score_request(
        self,
        surface_id: SurfaceId,
        strengths: dict[str, float],
        candidate_item_ids: list[str],
        rng: np.random.Generator,
    ) -> np.ndarray:
        """Empty backend never scores; raise to surface a programmer error."""
        raise RuntimeError(
            "EmptyLinTSInterestBackend.score_request called; guard with is_valid() before scoring."
        )

    def has_item(self, surface_id: SurfaceId, corpus_item_id: str) -> bool:
        """Empty backend knows no items."""
        return False

    def get_model_id(self, surface_id: SurfaceId) -> str | None:
        """Empty backend has no model id."""
        return None

    @property
    def update_count(self) -> int:
        """Empty backend never updates."""
        return 0
