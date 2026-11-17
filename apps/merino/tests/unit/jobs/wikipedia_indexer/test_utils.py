"""Unit tests for the utils module in wikipedia-indexer job"""

import base64
import csv
import io
import logging

import pytest
import requests
from pytest import LogCaptureFixture

from merino.jobs.wikipedia_indexer.utils import (
    ProgressReporter,
    build_blocked_titles_csv,
    create_blocklist,
    encode_offline_blocklist_title,
    latest_article_blocklist_blob,
    load_article_blocklist,
    upload_blocked_titles,
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


@pytest.mark.parametrize(
    "prefix",
    ["exports/article_blocklist", "exports/article_blocklist/", "/exports/article_blocklist"],
    ids=["no-slashes", "trailing-slash", "leading-slash"],
)
def test_latest_article_blocklist_blob(prefix):
    """Verify the writer and the reader agree on where the newest blocklist lives,
    however the prefix is slashed.
    """
    assert latest_article_blocklist_blob(prefix) == "exports/article_blocklist/latest.csv"


@pytest.mark.parametrize(
    ["title", "expected"],
    [
        ("Hercule Poirot", "hercule_poirot"),
        ("Paris, France", "paris,_france"),
        ("Île-de-France", "île-de-france"),
        ("Hercule_Poirot", "hercule_poirot"),
        ("Straße", "strasse"),
    ],
    ids=["spaces", "punctuation", "non-ascii", "underscores", "casefold"],
)
def test_encode_offline_blocklist_title(title, expected):
    """Verify titles are snake cased and casefolded before being base64 encoded."""
    encoded = encode_offline_blocklist_title(title)

    assert base64.b64decode(encoded).decode("utf-8") == expected


def test_build_blocked_titles_csv_is_consumable_by_the_offline_uploader():
    """Verify the CSV matches page view titles the way the offline uploader reads it."""
    content = build_blocked_titles_csv(["Hercule Poirot", "Paris, France", "hercule poirot"])

    # Same parsing as `top_n_by_frequency.get_top_n_frequency`.
    ignored = {
        base64.b64decode(item["title"]).decode("utf-8")
        for item in csv.DictReader(io.StringIO(content))
    }
    # Same check as `top_n_by_frequency.process`, on page view API titles.
    assert "Hercule_Poirot".casefold() in ignored
    assert "Paris,_France".casefold() in ignored
    # Duplicates after encoding are written once, in first-seen order.
    assert content.splitlines() == [
        "title",
        encode_offline_blocklist_title("Hercule Poirot"),
        encode_offline_blocklist_title("Paris, France"),
    ]


def test_build_blocked_titles_csv_without_titles():
    """Verify a run that blocked nothing still produces a valid, header-only CSV."""
    assert build_blocked_titles_csv([]) == "title\n"


@pytest.mark.parametrize(
    "destination",
    ["exports/blocked_titles", "exports/blocked_titles/", "/exports/blocked_titles/"],
    ids=["no-slashes", "trailing-slash", "leading-and-trailing-slashes"],
)
def test_upload_blocked_titles_writes_language_timestamped_csv_and_latest(
    storage_client, mocker, destination
):
    """Verify the CSV is uploaded as `{language}-{timestamp}.csv`, then copied to the
    language's own latest copy.
    """
    datetime = mocker.patch(f"{UTILS_MODULE}.datetime")
    datetime.now.return_value.strftime.return_value = "20261116120000"
    bucket = storage_client.return_value.bucket.return_value
    blob = bucket.blob.return_value
    blob.name = "exports/blocked_titles/fr-20261116120000.csv"

    name = upload_blocked_titles(["Hercule Poirot"], "bucket", destination, "a-project", "fr")

    assert name == "exports/blocked_titles/fr-20261116120000.csv"
    storage_client.assert_called_once_with(destination_gcp_project="a-project")
    storage_client.return_value.bucket.assert_called_once_with("bucket")
    bucket.blob.assert_called_once_with("exports/blocked_titles/fr-20261116120000.csv")
    blob.upload_from_string.assert_called_once_with(
        build_blocked_titles_csv(["Hercule Poirot"]), content_type="text/csv"
    )
    bucket.copy_blob.assert_called_once_with(blob, bucket, "exports/blocked_titles/fr-latest.csv")


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
