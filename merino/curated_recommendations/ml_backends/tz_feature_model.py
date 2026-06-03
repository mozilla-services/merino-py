"""Backend for the CTR-timezone score adjustment used by InterestRanker."""

import json
import logging
import tempfile
from datetime import datetime, timedelta, timezone
from functools import partial

import numpy as np
from safetensors import safe_open

from merino.curated_recommendations.corpus_backends.protocol import SurfaceId
from merino.utils.synced_gcs_blob import SyncedGcsBlob

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "tz_ratios_v1"
VALIDITY_PERIOD_MINUTES = 60

# Belt-and-suspenders clip on load in case the publisher's clip drifted.
SAFE_RATIO_LOW = 0.25
SAFE_RATIO_HIGH = 4.0


class TZFeatureBackend:
    """Per-surface backend that loads tz_ratios bundles and serves per-(item, tz) lookups."""

    def __init__(self, synced_gcs_blobs: dict[SurfaceId, SyncedGcsBlob]) -> None:
        self.synced_blobs: dict[SurfaceId, SyncedGcsBlob] = synced_gcs_blobs

        self._ratios: dict[SurfaceId, np.ndarray] = {}
        self._item_to_idx: dict[SurfaceId, dict[str, int]] = {}
        self._tz_labels: dict[SurfaceId, list[str]] = {}
        self._baseline_tz_index: dict[SurfaceId, int] = {}
        self._cache_time: dict[SurfaceId, datetime] = {}
        self._epoch_id: dict[SurfaceId, str] = {}

        for surface_id, blob in self.synced_blobs.items():
            blob.set_fetch_binary_callback(partial(self._fetch_callback, surface_id=surface_id))

    def _fetch_callback(self, data: bytes, surface_id: SurfaceId) -> None:
        """Parse a tz_ratios bundle and atomically install per-surface state."""
        try:
            parsed = self._parse_bundle(data)
        except Exception as e:
            logger.error(f"TZFeatureBackend: failed to parse bundle for {surface_id}: {e}")
            return

        self._ratios[surface_id] = parsed["ratios"]
        self._item_to_idx[surface_id] = parsed["item_to_idx"]
        self._tz_labels[surface_id] = parsed["tz_labels"]
        self._baseline_tz_index[surface_id] = parsed["baseline_tz_index"]
        self._cache_time[surface_id] = parsed["cache_time"]
        self._epoch_id[surface_id] = parsed["epoch_id"]

        logger.info(
            f"TZFeatureBackend: loaded {surface_id} "
            f"items={len(parsed['item_to_idx'])} "
            f"tz_labels={parsed['tz_labels']} "
            f"baseline_idx={parsed['baseline_tz_index']} "
            f"epoch={parsed['epoch_id']}"
        )

    @staticmethod
    def _parse_bundle(data: bytes) -> dict:
        """Validate + parse a tz_ratios bundle; raise on any mismatch."""
        with tempfile.NamedTemporaryFile(suffix=".safetensors") as tmp:
            tmp.write(data)
            tmp.flush()
            with safe_open(tmp.name, framework="numpy") as st:  # type: ignore[no-untyped-call]
                meta = st.metadata() or {}
                schema_version = meta.get("schema_version")
                if schema_version != SCHEMA_VERSION:
                    raise ValueError(
                        f"schema_version mismatch: got {schema_version!r}, "
                        f"expected {SCHEMA_VERSION!r}"
                    )
                ratios = st.get_tensor("ratios").copy()

        if ratios.dtype != np.float32:
            raise ValueError(f"ratios dtype mismatch: got {ratios.dtype}, expected float32")
        if ratios.ndim != 2:
            raise ValueError(f"ratios must be 2D, got shape {ratios.shape}")

        tz_labels = json.loads(meta["tz_labels"])
        if ratios.shape[1] != len(tz_labels):
            raise ValueError(
                f"ratios column count {ratios.shape[1]} does not match "
                f"len(tz_labels)={len(tz_labels)}"
            )
        baseline_tz = meta.get("baseline_tz")
        if baseline_tz not in tz_labels:
            raise ValueError(f"baseline_tz {baseline_tz!r} not present in tz_labels {tz_labels}")
        baseline_tz_index = tz_labels.index(baseline_tz)

        item_to_idx_raw = json.loads(meta["item_to_idx"])
        item_to_idx = {str(k): int(v) for k, v in item_to_idx_raw.items()}
        if len(item_to_idx) != ratios.shape[0]:
            raise ValueError(
                f"item_to_idx size {len(item_to_idx)} does not match "
                f"ratios.shape[0]={ratios.shape[0]}"
            )

        ratios = np.clip(ratios, SAFE_RATIO_LOW, SAFE_RATIO_HIGH)

        epoch_id = meta.get("epoch_id", "")
        try:
            cache_time = datetime.strptime(epoch_id, "%Y%m%d-%H%M").replace(tzinfo=timezone.utc)
        except ValueError:
            # Unparseable epoch → treat as already-stale.
            cache_time = datetime.fromtimestamp(0, tz=timezone.utc)

        return {
            "ratios": ratios,
            "item_to_idx": item_to_idx,
            "tz_labels": tz_labels,
            "baseline_tz_index": baseline_tz_index,
            "cache_time": cache_time,
            "epoch_id": epoch_id,
        }

    def is_valid(self, surface_id: SurfaceId) -> bool:
        """Return whether this surface has a fresh, well-formed bundle loaded."""
        cache_time = self._cache_time.get(surface_id)
        ratios = self._ratios.get(surface_id)
        if cache_time is None or ratios is None or ratios.size == 0:
            return False
        return datetime.now(timezone.utc) - cache_time <= timedelta(
            minutes=VALIDITY_PERIOD_MINUTES
        )

    def get_ratio(
        self,
        surface_id: SurfaceId,
        corpus_item_id: str,
        tz_index: int,
    ) -> float | None:
        """Return ratio for (item, user_tz), or None to signal no-adjustment.

        Returns 1.0 (no-op) when ``tz_index`` is the baseline TZ.
        """
        if not self.is_valid(surface_id):
            return None
        idx = self._item_to_idx[surface_id].get(str(corpus_item_id))
        if idx is None:
            return None
        n_cols = self._ratios[surface_id].shape[1]
        if tz_index < 0 or tz_index >= n_cols:
            return None
        if tz_index == self._baseline_tz_index[surface_id]:
            return 1.0
        return float(self._ratios[surface_id][idx, tz_index])

    def get_epoch_id(self, surface_id: SurfaceId) -> str | None:
        """Return the publish epoch_id for this surface, or None."""
        return self._epoch_id.get(surface_id)

    @property
    def update_count(self) -> int:
        """Total bundle refresh count across surfaces."""
        return sum(blob.update_count for blob in self.synced_blobs.values())


class EmptyTZFeatureBackend:
    """No-op stub used when the kill switch is off or GCS init fails."""

    def __init__(self) -> None:
        pass

    def is_valid(self, surface_id: SurfaceId) -> bool:
        """Return False; the stub never holds a valid bundle."""
        return False

    def get_ratio(
        self,
        surface_id: SurfaceId,
        corpus_item_id: str,
        tz_index: int,
    ) -> float | None:
        """Return None; the stub has no ratios."""
        return None

    def get_epoch_id(self, surface_id: SurfaceId) -> str | None:
        """Return None; the stub has no epoch."""
        return None

    @property
    def update_count(self) -> int:
        """Return 0; the stub never updates."""
        return 0
