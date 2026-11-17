"""Unit tests for the utils module in wikipedia-indexer job"""

import logging

import pytest
import requests
from pytest import LogCaptureFixture

from merino.jobs.wikipedia_indexer.utils import (
    ProgressReporter,
    create_blocklist,
    latest_article_blocklist_blob,
    load_article_blocklist,
)

UTILS_MODULE = "merino.jobs.wikipedia_indexer.utils"


@pytest.fixture()
def blocklist_csv_text():
    """Fixture for CSV contents for the blocklist."""
    with open("apps/merino/tests/data/blocklist.csv") as f:
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
        "Blocked category A",
        "Blocked category B",
        "Blocked category C",
    } == categories


def test_create_blocklist_raises_on_http_error(requests_mock):
    """Test that an HTTP error is raised rather than returning an empty blocklist."""
    url = "https://localhost"
    requests_mock.get(url, status_code=404, text="404: Not Found")  # nosec

    with pytest.raises(requests.HTTPError):
        create_blocklist(blocklist_file_url=url)


@pytest.fixture(name="storage_client")
def fixture_storage_client(mocker):
    """Patch the GCS client the article blocklist is downloaded with."""
    return mocker.patch(f"{UTILS_MODULE}.initialize_storage_client")


def _serve_csv(storage_client, text: str):
    """Make the patched client return `text` for any blob download."""
    blob = storage_client.return_value.bucket.return_value.blob.return_value
    blob.download_as_text.return_value = text


def test_load_article_blocklist_returns_qids(storage_client):
    """Verify the QID column of the latest blocklist is read, skipping rows without a QID."""
    _serve_csv(
        storage_client,
        'title,qid\r\nBlocked,Q1\r\n"Paris, France",Q90\r\nNo QID,\r\n',
    )

    qids = load_article_blocklist("bucket", "exports/article_blocklist", "a-project")

    assert qids == {"Q1", "Q90"}
    storage_client.assert_called_once_with(destination_gcp_project="a-project")
    client = storage_client.return_value
    client.bucket.assert_called_once_with("bucket")
    client.bucket.return_value.blob.assert_called_once_with("exports/article_blocklist/latest.csv")


def test_load_article_blocklist_raises_when_empty(storage_client):
    """Verify an empty blocklist fails rather than letting every article through."""
    _serve_csv(storage_client, "title,qid\r\n")

    with pytest.raises(RuntimeError, match="contains no QIDs"):
        load_article_blocklist("bucket", "prefix", "a-project")


def test_latest_article_blocklist_blob():
    """Verify the writer and the reader agree on where the newest blocklist lives."""
    assert latest_article_blocklist_blob("exports/article_blocklist") == (
        "exports/article_blocklist/latest.csv"
    )


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
