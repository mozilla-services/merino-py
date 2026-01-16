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
                self.get_cohort_for_interests.cache_clear()
            except Exception as e:
                logger.error(f"Failed to load cohort model {e}")

    @lru_cache(maxsize=5000)
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
        interest_bits = [int(c) for c in interests]
        try:
            with torch.no_grad():
                tensor_data = torch.tensor([interest_bits], dtype=torch.float32)
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
