"""Unit tests for the utils module in wikipedia-indexer job"""


import logging

import pytest
from pytest import LogCaptureFixture

from merino.jobs.wikipedia_indexer.util import ProgressReporter


@pytest.mark.parametrize(
    ["inputs", "expected_percs"],
    [
        ([0], [None]),
        ([1], [1]),
        ([1, 1], [1, None]),
        ([1, 10], [1, 10]),
        ([0, 1, 10], [None, 1, 10]),
        ([0, 1, 10, 10, 20], [None, 1, 10, None, 20]),
    ],
)
def test_progress_reporter(
    caplog: LogCaptureFixture, inputs: list[int], expected_percs: list[int | None]
):
    """Test progress reporter logs correctly."""
    logger = logging.getLogger("merino.test.log")
    caplog.set_level(logging.INFO)
    reporter = ProgressReporter(logger, "Test", "source", "destination", 100)
    for idx, input in enumerate(inputs):
        caplog.clear()
        reporter.report(input)
        expected_perc = expected_percs[idx]
        if expected_perc is None:
            assert len(caplog.records) == 0
        else:
            assert len(caplog.records) == 1
            assert caplog.records[0].message == f"Test progress: {expected_perc}%"
