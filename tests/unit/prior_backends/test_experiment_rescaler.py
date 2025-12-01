"""Module with basic tests covering the backend data rescaling used to normalize the
thompson sampling experiments
"""

from unittest.mock import Mock

from merino.curated_recommendations.corpus_backends.protocol import Topic
from merino.curated_recommendations.prior_backends.experiment_rescaler import (
    BLOCKED_FROM_MOST_POPULAR_SCALER,
    CrawledContentRescaler,
    SchedulerHoldbackRescaler,
    PESSIMISTIC_PRIOR_ALPHA_SCALE,
    PESSIMISTIC_PRIOR_ALPHA_SCALE_SUBTOPIC,
)

SECTIONS_HOLDBACK_TOTAL_PERCENT = 0.1
SUBTOPIC_EXPERIMENT_CURATED_ITEM_FLAG = "in_subtopic_experiment"


class TestDefaultRescaler:
    """Test Rig for the rescaler"""

    def setup_method(self):
        """Set up test"""
        self.rescaler = CrawledContentRescaler()

    def test_detect_blocked_from_most_popular(self):
        """Test detection of blocked from most popular"""
        rec = Mock()
        rec.in_experiment.return_value = True
        rec.topic = Topic.SPORTS
        assert self.rescaler.is_blocked_from_most_popular(rec)

        rec = Mock()
        rec.in_experiment.return_value = True
        rec.topic = Topic.ARTS
        assert not self.rescaler.is_blocked_from_most_popular(rec)

        rec.in_experiment.return_value = False
        rec.topic = Topic.GAMING
        assert self.rescaler.is_blocked_from_most_popular(rec)

        rec.topic = Topic.TECHNOLOGY
        assert not self.rescaler.is_blocked_from_most_popular(rec)

    def test_rescale_with_subtopic_item(self):
        """Test rescaling of priors for relative experiment size"""
        rec = Mock()
        rec.in_experiment.return_value = True  # Indicates subtopic for flag
        rec.isTimeSensitive = False
        expected_opens = 100
        expected_no_opens = 50
        opens, no_opens = self.rescaler.rescale(rec, expected_opens, expected_no_opens)
        assert opens == expected_opens
        assert no_opens == expected_no_opens

        alpha, beta = self.rescaler.rescale_prior(rec, 10, 20)
        assert alpha == 10 * PESSIMISTIC_PRIOR_ALPHA_SCALE_SUBTOPIC
        assert beta == 20

        assert self.rescaler.fresh_items_max == 0
        assert self.rescaler.fresh_items_section_ranking_max_percentage > 0
        assert self.rescaler.fresh_items_limit_prior_threshold_multiplier > 0

    def test_rescale_when_not_subtopic_item(self):
        """Test normal case for normal item"""
        rec = Mock()
        rec.in_experiment.return_value = False
        rec.isTimeSensitive = False

        opens, no_opens = self.rescaler.rescale(rec, 100, 50)
        assert opens == 100
        assert no_opens == 50

        alpha, beta = self.rescaler.rescale_prior(rec, 10, 20)
        assert alpha == 10 * PESSIMISTIC_PRIOR_ALPHA_SCALE
        assert beta == 20

    def test_rescale_opens_for_blocked_from_popular_item(self):
        """Test rescaling of opens for blocked Gaming item"""
        rec = Mock()
        rec.in_experiment.return_value = False
        rec.isTimeSensitive = False
        rec.topic = Topic.GAMING

        opens, no_opens = self.rescaler.rescale(rec, 100, 50)
        assert opens == 100 * BLOCKED_FROM_MOST_POPULAR_SCALER
        assert no_opens == 50 * BLOCKED_FROM_MOST_POPULAR_SCALER

    def test_rescale_opens_for_blocked_item(self):
        """Test rescaling of opens for blocked subtopic items"""
        rec = Mock()
        rec.in_experiment.return_value = True
        rec.isTimeSensitive = False
        rec.topic = Topic.GAMING

        opens, no_opens = self.rescaler.rescale(rec, 100, 50)
        assert opens == 100 * BLOCKED_FROM_MOST_POPULAR_SCALER
        assert no_opens == 50 * BLOCKED_FROM_MOST_POPULAR_SCALER

    def test_rescale_opens_for_non_blocked_item(self):
        """Test rescaling of opens for blocked subtopic items"""
        rec = Mock()
        rec.in_experiment.return_value = True
        rec.isTimeSensitive = False
        rec.topic = Topic.ARTS
        opens, no_opens = self.rescaler.rescale(rec, 100, 50)
        assert opens == 100
        assert no_opens == 50


class TestSchedulerHoldbackRescaler:
    """Test Rig for the rescaler"""

    def setup_method(self):
        """Set up test"""
        self.rescaler = SchedulerHoldbackRescaler()

    def test_rescale_subtopic_item(self):
        """Not an expected use case for legacy sections"""
        rec = Mock()
        rec.in_experiment.return_value = True
        opens, no_opens = self.rescaler.rescale(rec, 100, 50)
        expected_opens = 100 / SECTIONS_HOLDBACK_TOTAL_PERCENT
        expected_no_opens = 50 / SECTIONS_HOLDBACK_TOTAL_PERCENT
        assert opens == expected_opens
        assert no_opens == expected_no_opens

        alpha, beta = self.rescaler.rescale_prior(rec, 40, 20)
        assert alpha == 40
        assert beta == 20

        assert self.rescaler.fresh_items_max == 0
        assert self.rescaler.fresh_items_section_ranking_max_percentage == 0
        assert self.rescaler.fresh_items_limit_prior_threshold_multiplier == 0

    def test_rescale_regular_item(self):
        """Test when no experiment in request"""
        rec = Mock()
        rec.in_experiment.return_value = False
        rec.isTimeSensitive = False

        opens, no_opens = self.rescaler.rescale(rec, 100, 50)

        assert opens == 100 / SECTIONS_HOLDBACK_TOTAL_PERCENT
        assert no_opens == 50 / SECTIONS_HOLDBACK_TOTAL_PERCENT

        alpha, beta = self.rescaler.rescale_prior(rec, 40, 20)
        assert alpha == 40
        assert beta == 20

        assert self.rescaler.fresh_items_max == 0
        assert self.rescaler.fresh_items_section_ranking_max_percentage == 0
        assert self.rescaler.fresh_items_limit_prior_threshold_multiplier == 0
