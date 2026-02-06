"""Module dedicated to backends for Thompson sampling priors loaded from GCS."""

from datetime import datetime
import torch
import tempfile
from safetensors.torch import safe_open
import logging
from functools import lru_cache

from merino.curated_recommendations.ml_backends.interest_cohort_model import InterestCohortModel
from merino.curated_recommendations.ml_backends.protocol import (
    CohortModelBackend,
)
from merino.utils.synced_gcs_blob import SyncedGcsBlob

logger = logging.getLogger(__name__)

DEFAULT_TARGET_COHORTS = 10
DO_EMPTY_COHORT_FOR_NO_CLICKS = True
NO_CLICKS_COHORT_ID = "-1"


class GcsInterestCohortModel(CohortModelBackend):
    """Backend that fetches ML Recs from GCS for Contextual Ranker"""

    def __init__(self, synced_gcs_blob: SyncedGcsBlob) -> None:
        self.synced_blob = synced_gcs_blob
        self.synced_blob.set_fetch_binary_callback(self._fetch_binary_callback)
        self.cache_time: datetime | None = None
        self._model_id: str | None = None
        self._num_bits: int = 0
        self._target_cohorts: int = DEFAULT_TARGET_COHORTS

    def _fetch_binary_callback(self, data: bytes) -> None:
        """Process the raw blob data and update the cache atomically."""
        with tempfile.NamedTemporaryFile(suffix=".safetensors") as tmp:
            tmp.write(data)
            tmp.flush()
            try:
                with safe_open(tmp.name, framework="pt") as f:  # type: ignore[no-untyped-call]
                    metadata = f.metadata() or {}
                    self._model_id = metadata.get("model_id", "unknown")
                    self._num_bits = int(metadata.get("num_interest_bits", 32))
                    if self._num_bits == 40:
                        self._num_bits = 32  # backwards compatibility hack, as external inputs are still 40 bits. Will remove later.
                    self._training_run_id = metadata.get("training_run_id", "unknown")
                    self._target_cohorts = int(
                        metadata.get("target_cohorts", DEFAULT_TARGET_COHORTS)
                    )
                    state_dict = {}
                    for key in f.keys():
                        state_dict[key] = f.get_tensor(key)
                cohort_model = InterestCohortModel(
                    target_cohorts=self._target_cohorts, num_interest_bits=self._num_bits
                )
                cohort_model.load_state_dict(state_dict)
                self._cohort_model = cohort_model
                self._cohort_model.eval()
                self._get_cohort_for_normalized_interests.cache_clear()
            except Exception as e:
                logger.error(f"Failed to load cohort model {e}")

    def _normalize_interests(self, interests: str) -> str | None:
        """Normalize the interests string into a string with simpler patterns."""
        if len(interests) != self._num_bits:
            return None

        # Mapping equivalent to the CASE / REGEXP_CONTAINS logic
        replacement_map = {
            "1010": "0100",
            "1100": "0100",
            "0101": "0010",
            "0110": "0010",
            "0011": "0010",
            "1000": "1000",
            "0100": "0100",
            "0010": "0010",
            "0001": "0001",
        }
        normalized_chunks = []
        # Process in 4-bit chunks
        for i in range(0, self._num_bits, 4):
            chunk = interests[i : i + 4]
            normalized_chunks.append(replacement_map.get(chunk, "0000"))
        return "".join(normalized_chunks)

    def _is_empty_cohort_for_no_clicks(self, normalized_interests: str) -> bool:
        """Determine if the normalized interests correspond to the empty cohort for no clicks."""
        if not DO_EMPTY_COHORT_FOR_NO_CLICKS:
            return False
        for k in range(self._num_bits // 4):
            chunk = normalized_interests[k * 4 : (k + 1) * 4]
            if (
                chunk != "0000" and chunk != "1000"
            ):  # if any chunk has more than the least significant bit set, it's not the no-clicks cohort
                return False
        return True

    def get_cohort_for_interests(
        self,
        interests: str,
        model_id: str,
        training_run_id: str | None = None,
    ) -> str | None:
        """Fetch the contextual ranking cohort based on interests string.
        Requires Model ID to match, and also checks training_run_id if provided.
        """
        if self._model_id != model_id or self._model_id is None:
            return None
        if len(interests) != self._num_bits:
            return None
        if training_run_id is not None and self._training_run_id != training_run_id:
            return None
        normalized_interests: str | None = self._normalize_interests(interests)
        if normalized_interests is None:
            return None
        else:
            if self._is_empty_cohort_for_no_clicks(normalized_interests):
                return NO_CLICKS_COHORT_ID
            return self._get_cohort_for_normalized_interests(normalized_interests)

    @lru_cache(maxsize=3000)
    def _get_cohort_for_normalized_interests(
        self,
        normalized_interests: str,
    ) -> str | None:
        """Fetch the contextual ranking cohort based on normalized interests list.
        Requires Model ID to match, and also checks training_run_id if provided.
        """
        bit_values = [int(bit) for bit in normalized_interests]
        try:
            with torch.no_grad():
                tensor_data = torch.tensor([bit_values], dtype=torch.float32)
                results = self._cohort_model(tensor_data).argmax(dim=1)
                return str(results[0].item())
        except Exception as e:
            logger.error(f"Error during model inference: {e}")
            return None

    @property
    def update_count(self) -> int:
        """Return the number of times the ml data has been updated."""
        return self.synced_blob.update_count


class EmptyCohortModel(CohortModelBackend):
    """Empty Backend that fetches ML Recs from GCS for Contextual Ranker"""

    def __init__(self) -> None:
        pass

    def get_cohort_for_interests(
        self,
        interests: str,
        model_id: str,
        training_run_id: str | None = None,
    ) -> str | None:
        """Fetch the contextual ranking cohort based on interests string."""
        return None
