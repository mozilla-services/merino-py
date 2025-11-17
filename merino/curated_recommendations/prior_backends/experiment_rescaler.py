"""Rescaler of engagement for experiments"""

from typing import Any

from merino.curated_recommendations.prior_backends.protocol import ExperimentRescaler
from merino.curated_recommendations.protocol import CuratedRecommendation

SECTIONS_HOLDBACK_TOTAL_PERCENT = 0.1
SUBTOPIC_EXPERIMENT_CURATED_ITEM_FLAG = "SUBTOPICS"

# Subtopic prior scaling is derived using data analysis on scores and existing priors
# See more at:
# https://mozilla-hub.atlassian.net/wiki/spaces/FAAMT/pages/1727725665/Thompson+Sampling+of+Subtopic+Sections
PESSIMISTIC_PRIOR_ALPHA_SCALE = 0.4
PESSIMISTIC_PRIOR_ALPHA_SCALE_SUBTOPIC = 0.35


class DefaultCrawlerRescaler(ExperimentRescaler):
    """Scales based on overall percentage"""

    def __init__(self, **data: Any):
        data.setdefault("fresh_items_max", 0)
        data.setdefault("fresh_items_top_stories_max_percentage", 0.15)
        data.setdefault("fresh_items_section_ranking_max_percentage", 0.15)
        data.setdefault("fresh_items_limit_prior_threshold_multiplier", 1)
        super().__init__(**data)

    @classmethod
    def is_subtopic_story(cls, rec: CuratedRecommendation) -> bool:
        """Story is part of an experiment"""
        return rec.in_experiment(SUBTOPIC_EXPERIMENT_CURATED_ITEM_FLAG)

    def rescale(self, rec: CuratedRecommendation, opens: float, no_opens: float):
        """Update open and non-open values based on whether item is unique to the experiment"""
        return opens, no_opens

    def rescale_prior(self, rec: CuratedRecommendation, alpha, beta):
        """Update priors values based on whether item is unique to the experiment.
        Scale of 4 puts an item with no activity just below the pack of common items that have good activity
        """
        if rec.isTimeSensitive:
            return alpha, beta
        if self.is_subtopic_story(rec):
            return alpha * PESSIMISTIC_PRIOR_ALPHA_SCALE_SUBTOPIC, beta
        else:
            return alpha * PESSIMISTIC_PRIOR_ALPHA_SCALE, beta


class SchedulerHoldbackRescaler(ExperimentRescaler):
    """Scales experiment based content on relative size of experiment, as a fractional percentage"""

    def __init__(self, **data: Any):
        super().__init__(**data)

    def rescale(self, rec: CuratedRecommendation, opens: float, no_opens: float):
        """Update open and non-open values based on whether item is unique to the experiment"""
        return opens / SECTIONS_HOLDBACK_TOTAL_PERCENT, no_opens / SECTIONS_HOLDBACK_TOTAL_PERCENT

    def rescale_prior(self, rec: CuratedRecommendation, alpha, beta):
        """Rescales priors based on content"""
        return alpha, beta
