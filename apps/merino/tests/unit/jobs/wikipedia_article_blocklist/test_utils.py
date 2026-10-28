"""Unit tests for the utils module in the wikipedia article blocklist job."""

import pytest
import requests

from merino.jobs.wikipedia_article_blocklist.utils import create_blocklist


@pytest.fixture()
def blocklist_csv_text():
    """Fixture for CSV contents for the blocklist."""
    with open("apps/merino/tests/data/blocklist.csv") as f:
        return f.read()


def test_create_blocklist(requests_mock, blocklist_csv_text: str):
    """Test that the blocklist is created from CSV file."""
    url = "https://localhost"
    requests_mock.get(url, text=blocklist_csv_text)  # nosec

    categories = create_blocklist(blocklist_file_url=url)

    assert {"Child abuse", "Orgasm", "Paraphilias"} == categories


def test_create_blocklist_raises_on_http_error(requests_mock):
    """Test that an HTTP error is raised rather than returning an empty blocklist."""
    url = "https://localhost"
    requests_mock.get(url, status_code=404, text="404: Not Found")  # nosec

    with pytest.raises(requests.HTTPError):
        create_blocklist(blocklist_file_url=url)
