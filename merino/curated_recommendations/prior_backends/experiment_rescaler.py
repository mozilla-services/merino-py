"""Rescaler of engagement for experiments"""

from typing import Any

from merino.curated_recommendations.prior_backends.protocol import ExperimentRescaler
from merino.curated_recommendations.protocol import CuratedRecommendation

SUBSECTION_EXPERIMENT_PERCENT = 0.03  # This may eventually be computed by an airflow job
SUBTOPIC_EXPERIMENT_CURATED_ITEM_FLAG = "SUBTOPICS"


class SubsectionsExperimentRescaler(ExperimentRescaler):
    """Scales experiment based content on relative size of experiment, as a fractional percentage"""

    def __init__(self, **data: Any):
        data.setdefault("experiment_relative_size", SUBSECTION_EXPERIMENT_PERCENT)
        super().__init__(**data)

    @classmethod
    def is_experiment_story(cls, rec: CuratedRecommendation) -> bool:
        """Story is part of an experiment"""
        return rec.in_experiment(SUBTOPIC_EXPERIMENT_CURATED_ITEM_FLAG)

    def rescale(self, rec: CuratedRecommendation, opens: float, no_opens: float):
        """Update open and non-open values based on whether item is unique to the experiment"""
        if self.is_experiment_story(rec):
            return opens / self.experiment_relative_size, no_opens / self.experiment_relative_size
        else:
            return opens, no_opens

    def rescale_prior(self, rec: CuratedRecommendation, alpha, beta):
        """Update priors values based on whether item is unique to the experiment.
        Scale of 4 puts an item with no activity just below the pack of common items that have good activity
        """
        if self.is_experiment_story(rec):
            return alpha / 4.0, beta
        else:
            return alpha, beta
