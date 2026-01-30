"""Unit tests for the utils module in wikipedia-indexer job"""

import logging

import pytest
from pytest import LogCaptureFixture

from merino.jobs.wikipedia_indexer.utils import (
    ProgressReporter,
    create_blocklist,
)


@pytest.fixture()
def blocklist_csv_text():
    """Fixture for CSV contents for the blocklist."""
    with open("tests/data/blocklist.csv") as f:
        return f.read()


def test_create_blocklist(
    requests_mock,
    blocklist_csv_text: str,
):
    """Test that the blocklist is created from CSV file."""
    url = "https://localhost"
    requests_mock.get(url, text=blocklist_csv_text)  # nosec

    categories = create_blocklist(blocklist_file_url=url)

    assert {
        "Child abuse",
        "Orgasm",
        "Paraphilias",
    } == categories


@pytest.mark.parametrize(
    ["inputs", "expected_percs"],
    [
        ([(0, 0)], [None]),
        ([(1, 0)], [1]),
        ([(1, 0), (1, 0)], [1, None]),
        ([(1, 0), (1, 5)], [1, 6]),
        ([(1, 0), (10, 0)], [1, 10]),
        ([(0, 0), (1, 0), (10, 0)], [None, 1, 10]),
        ([(0, 0), (1, 5), (10, 5), (10, 5), (20, 5)], [None, 6, 15, None, 25]),
    ],
    ids=[
        "None indexed",
        "Indexed completed",
        "No change reported",
        "Blocked reported",
        "Indexed progress reported",
        "Indexed progress reported with start",
        "Indexed progress composite",
    ],
)
def test_progress_reporter(
    caplog: LogCaptureFixture,
    inputs: list[tuple[int, int]],
    expected_percs: list[int | None],
):
    """Test progress reporter logs correctly."""
    logger = logging.getLogger("merino.test.log")
    caplog.set_level(logging.INFO)
    reporter = ProgressReporter(logger, "Test", "source", "destination", 100)
    for idx, (indexed, blocked) in enumerate(inputs):
        caplog.clear()
        reporter.report(indexed, blocked)
        expected_perc = expected_percs[idx]
        if expected_perc is None:
            assert len(caplog.records) == 0
        else:
            assert len(caplog.records) == 1
            assert caplog.records[0].message == f"Test progress: {expected_perc}%"
