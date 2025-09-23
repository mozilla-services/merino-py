"""Module with basic tests covering the backend data rescaling used to normalize the
thompson sampling experiments
"""

from unittest.mock import Mock

from merino.curated_recommendations.prior_backends.experiment_rescaler import (
    SubsectionsExperimentRescaler,
    CRAWLED_TOPIC_TOTAL_PERCENT,
    CrawlerExperimentRescaler,
    PESSIMISTIC_PRIOR_ALPHA_SCALE,
)

SUBSECTION_EXPERIMENT_PERCENT = 0.25
SUBTOPIC_EXPERIMENT_CURATED_ITEM_FLAG = "in_subtopic_experiment"


class TestSubsectionsExperimentRescaler:
    """Test Rig for the rescaler"""

    def setup_method(self):
        """Set up test"""
        self.rescaler = SubsectionsExperimentRescaler(
            subtopic_relative_size=SUBSECTION_EXPERIMENT_PERCENT
        )

    def test_rescale_when_in_experiment(self):
        """Test rescaling of priors for relative experiment size"""
        rec = Mock()
        rec.in_experiment.return_value = True
        opens, no_opens = self.rescaler.rescale(rec, 100, 50)
        expected_opens = 100 / SUBSECTION_EXPERIMENT_PERCENT
        expected_no_opens = 50 / SUBSECTION_EXPERIMENT_PERCENT
        assert opens == expected_opens
        assert no_opens == expected_no_opens

        alpha, beta = self.rescaler.rescale_prior(rec, 10, 20)
        assert alpha == 10 / 4.0
        assert beta == 20

    def test_rescale_when_not_in_experiment(self):
        """Test when no experiment in request"""
        rec = Mock()
        rec.in_experiment.return_value = False

        opens, no_opens = self.rescaler.rescale(rec, 100, 50)

        assert opens == 100
        assert no_opens == 50


class TestCrawlerExperimentRescaler:
    """Test Rig for the rescaler"""

    def setup_method(self):
        """Set up test"""
        self.rescaler = CrawlerExperimentRescaler(
            subtopic_relative_size=SUBSECTION_EXPERIMENT_PERCENT
        )

    def test_rescale_subtopic_item(self):
        """Test rescaling of priors for relative experiment size"""
        rec = Mock()
        rec.in_experiment.return_value = True
        rec.isTimeSensitive = False
        opens, no_opens = self.rescaler.rescale(rec, 100, 50)
        expected_opens = 100 / SUBSECTION_EXPERIMENT_PERCENT
        expected_no_opens = 50 / SUBSECTION_EXPERIMENT_PERCENT
        assert opens == expected_opens
        assert no_opens == expected_no_opens

        alpha, beta = self.rescaler.rescale_prior(rec, 40, 20)

        assert alpha == 40 * PESSIMISTIC_PRIOR_ALPHA_SCALE
        assert beta == 20

    def test_rescale_regular_item(self):
        """Test when no experiment in request"""
        rec = Mock()
        rec.in_experiment.return_value = False
        rec.isTimeSensitive = False

        opens, no_opens = self.rescaler.rescale(rec, 100, 50)

        assert opens == 100 / CRAWLED_TOPIC_TOTAL_PERCENT
        assert no_opens == 50 / CRAWLED_TOPIC_TOTAL_PERCENT

        alpha, beta = self.rescaler.rescale_prior(rec, 40, 20)

        assert alpha == 40 * PESSIMISTIC_PRIOR_ALPHA_SCALE
        assert beta == 20

    def test_rescale_regular_boosted_item(self):
        """Test when no experiment in request"""
        rec = Mock()
        rec.in_experiment.return_value = False
        rec.isTimeSensitive = True
        opens, no_opens = self.rescaler.rescale(rec, 100, 50)

        assert opens == 100 / CRAWLED_TOPIC_TOTAL_PERCENT
        assert no_opens == 50 / CRAWLED_TOPIC_TOTAL_PERCENT

        alpha, beta = self.rescaler.rescale_prior(rec, 40, 20)

        # alpha, beta are unchanged
        assert alpha == 40
        assert beta == 20
