"""Module with basic tests covering the backend data rescaling used to normalize the
thompson sampling experiments
"""

from unittest.mock import Mock

from merino.curated_recommendations.prior_backends.experiment_rescaler import (
    DefaultCrawlerRescaler,
    SchedulerHoldbackRescaler,
    PESSIMISTIC_PRIOR_ALPHA_SCALE,
)

SECTIONS_HOLDBACK_TOTAL_PERCENT = 0.1
SUBTOPIC_EXPERIMENT_CURATED_ITEM_FLAG = "in_subtopic_experiment"


class TestDefaultRescaler:
    """Test Rig for the rescaler"""

    def setup_method(self):
        """Set up test"""
        self.rescaler = DefaultCrawlerRescaler()

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
        assert alpha == 10 * PESSIMISTIC_PRIOR_ALPHA_SCALE
        assert beta == 20

    def test_rescale_when_not_subtopic_item(self):
        """Test when no experiment in request"""
        rec = Mock()
        rec.in_experiment.return_value = False
        rec.isTimeSensitive = False

        opens, no_opens = self.rescaler.rescale(rec, 100, 50)
        assert opens == 100
        assert no_opens == 50

        alpha, beta = self.rescaler.rescale_prior(rec, 10, 20)
        assert alpha == 10
        assert beta == 20


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
