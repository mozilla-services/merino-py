"""Rescaler of engagement for experiments"""

from typing import Any

from merino.curated_recommendations.prior_backends.protocol import ExperimentRescaler
from merino.curated_recommendations.protocol import CuratedRecommendation

SUBTOPIC_TOTAL_PERCENT = 0.13  # This may eventually be computed by an airflow job
CRAWLED_TOPIC_TOTAL_PERCENT = 0.13
SUBTOPIC_EXPERIMENT_CURATED_ITEM_FLAG = "SUBTOPICS"

# This is derived using data analysis on scores and existing priors
# See more at:
# https://mozilla-hub.atlassian.net/wiki/spaces/FAAMT/pages/1727725665/Thompson+Sampling+of+Subtopic+Sections
PESSIMISTIC_PRIOR_ALPHA_SCALE = 0.20


class SubsectionsExperimentRescaler(ExperimentRescaler):
    """Scales experiment based content on relative size of experiment, as a fractional percentage"""

    subtopic_relative_size: float

    def __init__(self, **data: Any):
        data.setdefault("subtopic_relative_size", SUBTOPIC_TOTAL_PERCENT)
        super().__init__(**data)

    @classmethod
    def is_subtopic_story(cls, rec: CuratedRecommendation) -> bool:
        """Story is part of an experiment"""
        return rec.in_experiment(SUBTOPIC_EXPERIMENT_CURATED_ITEM_FLAG)

    def rescale(self, rec: CuratedRecommendation, opens: float, no_opens: float):
        """Update open and non-open values based on whether item is unique to the experiment"""
        if self.is_subtopic_story(rec):
            return opens / self.subtopic_relative_size, no_opens / self.subtopic_relative_size
        else:
            return opens, no_opens

    def rescale_prior(self, rec: CuratedRecommendation, alpha, beta):
        """Update priors values based on whether item is unique to the experiment.
        Scale of 4 puts an item with no activity just below the pack of common items that have good activity
        """
        if self.is_subtopic_story(rec):
            return alpha * PESSIMISTIC_PRIOR_ALPHA_SCALE, beta
        else:
            return alpha, beta


class CrawlerExperimentRescaler(SubsectionsExperimentRescaler):
    """Scales experiment based content on relative size of experiment, as a fractional percentage"""

    crawled_relative_size: float

    def __init__(self, **data: Any):
        data.setdefault("crawled_relative_size", CRAWLED_TOPIC_TOTAL_PERCENT)
        super().__init__(**data)

    def rescale(self, rec: CuratedRecommendation, opens: float, no_opens: float):
        """Update open and non-open values based on whether item is unique to the experiment"""
        if self.is_subtopic_story(rec):
            return opens / self.subtopic_relative_size, no_opens / self.subtopic_relative_size
        else:
            return opens / self.crawled_relative_size, no_opens / self.crawled_relative_size

    def rescale_prior(self, rec: CuratedRecommendation, alpha, beta):
        """Rescales priors based on content"""
        if rec.isTimeSensitive:
            # We are using the timeSensitive flag as a means for editors to boost content
            # The unmodified alpha, beta has an optimistic prior, bringing new content to the top
            return alpha, beta
        # Default - data comes in with a lower expected CTR in order to not severely disrupt popular items
        return alpha * PESSIMISTIC_PRIOR_ALPHA_SCALE, beta
