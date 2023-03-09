"""Unit tests for the utils module in wikipedia-indexer job"""


import logging
from unittest.mock import ANY

import pytest
from elasticsearch import Elasticsearch
from pytest import LogCaptureFixture
from pytest_mock import MockerFixture

from merino.jobs.wikipedia_indexer.util import (
    ProgressReporter,
    create_blocklist,
    create_elasticsearch_client,
)


@pytest.fixture()
def blocklist_csv_text():
    """Fixture for CSV contents for the blocklist."""
    with open("tests/data/blocklist.csv") as f:
        return f.read()


def test_create_blocklist(requests_mock, blocklist_csv_text: str):
    """Test that the blocklist is created from CSV file."""
    url = "https://localhost"
    requests_mock.get(url, text=blocklist_csv_text)

    categories = create_blocklist(url)
    assert {"Child abuse", "Orgasm", "Paraphilias"} == categories


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


def test_create_elasticsearch_client_url(mocker: MockerFixture):
    """Test that Elasticsearch client is created with the URL."""
    es_new_mock = mocker.patch.object(Elasticsearch, "__new__")

    api_key = "mMyY2E2ZDA0MjI0OWFmMGNjN2Q3YTllOTYyNTc0Mw=="
    url = "http://localhost:9200"

    # Have the cloud id for checking that it doesn't get called with this.
    cloud_id = (
        "testing:dXMtZWFzdC0xLmF3cy5mb3VuZC5pbyRjZ"
        "WM2ZjI2MWE3NGJmMjRjZTMzYmI4ODExYjg0Mjk0Zi"
        "RjNmMyY2E2ZDA0MjI0OWFmMGNjN2Q3YTllOTYyNTc0Mw=="
    )

    create_elasticsearch_client(url, cloud_id, api_key)

    # First argument is "self", which I've stubbed with ANY
    es_new_mock.assert_called_with(ANY, url, api_key=api_key, request_timeout=60)


def test_create_elasticsearch_client_cloud_id(mocker: MockerFixture):
    """Test that Elasticsearch client is created with the Cloud."""
    es_new_mock = mocker.patch.object(Elasticsearch, "__new__")

    api_key = "mMyY2E2ZDA0MjI0OWFmMGNjN2Q3YTllOTYyNTc0Mw=="
    url = ""
    cloud_id = (
        "testing:dXMtZWFzdC0xLmF3cy5mb3VuZC5pbyRjZ"
        "WM2ZjI2MWE3NGJmMjRjZTMzYmI4ODExYjg0Mjk0Zi"
        "RjNmMyY2E2ZDA0MjI0OWFmMGNjN2Q3YTllOTYyNTc0Mw=="
    )

    create_elasticsearch_client(url, cloud_id, api_key)

    # First argument is "self", which I've stubbed with ANY
    es_new_mock.assert_called_with(
        ANY, cloud_id=cloud_id, api_key=api_key, request_timeout=60
    )
