"""Module dedicated to backends for Thompson sampling priors loaded from GCS."""

from datetime import datetime
import torch
from safetensors.torch import safe_open
import logging
from functools import lru_cache

from merino.curated_recommendations.ml_backends.interest_cohort_model import InterestCohortModel
from merino.curated_recommendations.ml_backends.protocol import (
    CohortModelBackend,
)
from merino.utils.synced_gcs_blob import SyncedGcsBlob

logger = logging.getLogger(__name__)


class GcsInterestCohortModel(CohortModelBackend):
    """Backend that fetches ML Recs from GCS for Contextual Ranker"""

    def __init__(self, synced_gcs_blob: SyncedGcsBlob) -> None:
        self.synced_blob = synced_gcs_blob
        self.synced_blob.set_fetch_callback(self._fetch_callback)
        self.cache_time: datetime | None = None

    def _fetch_callback(self, data: bytes | str) -> None:
        """Process the raw blob data and update the cache atomically."""
        cohort_model = InterestCohortModel()
        cohort_model.load_state_dict(data)
        with safe_open(data, framework="pt") as f:
            metadata = f.metadata()
            self._model_id = metadata.get("model_id", "unknown")
            self._num_bits = metadata.get("num_interest_bits", 32)
            self._training_run_id = metadata.get("training_run_id", "unknown")
        self._cohort_model = cohort_model
        self._cohort_model.eval()
        self.get_chohort_for_interests.cache_clear()

    @lru_cache(maxsize=5000)
    def get_cohort_for_interests(
        self,
        interests: str,
        model_id,
        training_run_id: str | None = None,
    ) -> int | None:
        """Fetch the contextual ranking cohort based on interests string."""
        if self._model_id != model_id or self._model_id is None:
            return None
        if len(interests) != self._num_bits:
            return None
        if training_run_id is not None and self._training_run_id != training_run_id:
            return None
        interest_bits = [int(c) for c in interests]
        with torch.no_grad():
            tensor_data = torch.tensor([interest_bits], dtype=torch.float32)
            results = self._cohort_model(tensor_data).argmax(dim=1)
            return results[0].item()

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
        model_id,
        training_run_id: str | None = None,
    ) -> int | None:
        """Fetch the contextual ranking cohort based on interests string."""
        return None
