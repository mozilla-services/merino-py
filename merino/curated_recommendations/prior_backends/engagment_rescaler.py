"""Rescaler of engagement for various content types and experiments"""

from typing import Any

from merino.curated_recommendations.prior_backends.protocol import EngagementRescaler
from merino.curated_recommendations.protocol import ITEM_SUBTOPIC_FLAG, CuratedRecommendation

SECTIONS_HOLDBACK_TOTAL_PERCENT = 0.1

# Looking at query of typical subtopic impressions outside of top stories
# https://sql.telemetry.mozilla.org/queries/112921/source#276948
# We can see that for a typical section like NFL, impressions are about 4x lower than the overall average
# compared to stories that can appear in top stories. Just to be safe we are scaling down 5x.
BLOCKED_FROM_MOST_POPULAR_SCALER = 5.0

# Subtopic prior scaling is derived using data analysis on scores and existing priors
# See more at:
# https://mozilla-hub.atlassian.net/wiki/spaces/FAAMT/pages/1727725665/Thompson+Sampling+of+Subtopic+Sections
PESSIMISTIC_PRIOR_ALPHA_SCALE = 0.4
PESSIMISTIC_PRIOR_ALPHA_SCALE_SUBTOPIC = 0.35


class CrawledContentRescaler(EngagementRescaler):
    """Rescaler that has settings for any Crawl type deployment that has many content item updates throughout the day
    Special handling is added for certain content types that are blocked from most popular section
    """

    def __init__(self, **data: Any):
        data.setdefault("fresh_items_max", 0)
        data.setdefault("fresh_items_top_stories_max_percentage", 0.15)
        data.setdefault("fresh_items_section_ranking_max_percentage", 0.15)
        data.setdefault("fresh_items_limit_prior_threshold_multiplier", 1)
        super().__init__(**data)

    @classmethod
    def is_subtopic_story(cls, rec: CuratedRecommendation) -> bool:
        """Story is a subtopic that is not manually curated. Currently this is true for all non-legacy sections that not manually curated"""
        return rec.in_experiment(ITEM_SUBTOPIC_FLAG)

    @classmethod
    def is_blocked_from_most_popular(cls, rec: CuratedRecommendation) -> bool:
        """Return true if the story is blocked from most popular section.
        Note that this logic is duplicated in ArticleBalancer
        """
        return rec.is_story_blocked_for_top_stories()

    def rescale(self, rec: CuratedRecommendation, opens: float, no_opens: float):
        """Story is not allowed in most popular in some cases. We therefore will have to get by with many less impressions
        If we don't do this, these stories will rely more on priors for ranking, causing poor exploration/exploitation balance
        both in terms of section ranking and ranking within the section
        """
        if self.is_blocked_from_most_popular(rec):
            opens = opens * BLOCKED_FROM_MOST_POPULAR_SCALER
            no_opens = no_opens * BLOCKED_FROM_MOST_POPULAR_SCALER
        return opens, no_opens

    def rescale_prior(self, rec: CuratedRecommendation, alpha, beta):
        """Update priors values based on whether item is unique to the experiment.
        Scale of 0.25 puts an item with no activity just below the pack of common items that have good activity

        For default case we lower priors for gaming and subtopic stories to be more pessimistic in terms of CTR
        """
        if rec.isTimeSensitive:
            return alpha, beta
        if self.is_subtopic_story(rec) or self.is_blocked_from_most_popular(rec):
            return alpha * PESSIMISTIC_PRIOR_ALPHA_SCALE_SUBTOPIC, beta
        else:
            return alpha * PESSIMISTIC_PRIOR_ALPHA_SCALE, beta


class UKCrawledContentRescaler(CrawledContentRescaler):
    """Rescaler that has settings for any Crawl type deployment that has many content item updates throughout the day
    Special handling is added for certain content types that are blocked from most popular section
    """

    def __init__(self, **data: Any):
        super().__init__(**data)

    def rescale(self, rec: CuratedRecommendation, opens: float, no_opens: float):
        """Story is not allowed in most popular in some cases. We therefore will have to get by with many less impressions
        If we don't do this, these stories will rely more on priors for ranking, causing poor exploration/exploitation balance
        both in terms of section ranking and ranking within the section
        """
        opens, no_opens = super().rescale(rec, opens, no_opens)
        return opens, no_opens


class SchedulerHoldbackRescaler(EngagementRescaler):
    """Scales experiment based content on relative size of experiment, as a fractional percentage"""

    def __init__(self, **data: Any):
        super().__init__(**data)

    def rescale(self, rec: CuratedRecommendation, opens: float, no_opens: float):
        """Update open and non-open values based on whether item is unique to the experiment"""
        return opens / SECTIONS_HOLDBACK_TOTAL_PERCENT, no_opens / SECTIONS_HOLDBACK_TOTAL_PERCENT

    def rescale_prior(self, rec: CuratedRecommendation, alpha, beta):
        """Rescales priors based on content"""
        return alpha, beta
