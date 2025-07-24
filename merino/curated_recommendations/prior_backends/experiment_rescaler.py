"""Rescaler of engagement for experiments"""

from typing import Optional

from merino.curated_recommendations.corpus_backends.protocol import SurfaceId
from merino.curated_recommendations.localization import LOCALIZED_SECTION_TITLES
from merino.curated_recommendations.prior_backends.protocol import ExperimentRescaler
from merino.curated_recommendations.protocol import CuratedRecommendation, Section

SUBSECTION_EXPERIMENT_PERCENT = 0.03  # This will eventually be computed by an airflow job


class SubsectionsExperimentRescaler(ExperimentRescaler):
    """Scales experiment based content on relative size of experiment"""

    cur_recs: dict[str, Section]
    experiment_additional_content_id: Optional[set] = None

    def __init__(self, **data):
        data.setdefault('experiment_name', "sf")
        data.setdefault('experiment_branch', "treatment")
        data.setdefault('target_region', "EN_US")
        data.setdefault('experiment_relative_size', SUBSECTION_EXPERIMENT_PERCENT)
        super().__init__(**data)

    def model_post_init(self, __context) -> None:
        """Complete setup for experiment by looking up items in/out of experiment"""
        self.experiment_additional_content_id = set()
        for section_name, section in self.cur_recs.items():
            if not self.is_legacy_section(section_name):
                self.experiment_additional_content_id.update([rec.corpusItemId for rec in section.recommendations])

    def is_legacy_section(self, section_id):
        """Section id is part of the standard set of sections (vs a subtopic)"""
        return section_id in LOCALIZED_SECTION_TITLES[SurfaceId.NEW_TAB_EN_US]

    def is_experiment_story(self, rec: CuratedRecommendation):
        """Story is part of an experiment"""
        return rec.corpusItemId in self.experiment_additional_content_id

    def rescale(self, rec: CuratedRecommendation, opens: float, no_opens: float):
        """Update open and non-open values based on whether item is unique to the experiment"""
        if self.is_experiment_story(rec):
            return opens / self.experiment_relative_size, no_opens / self.experiment_relative_size
        else:
            return opens, no_opens
