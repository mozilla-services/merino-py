"""FileManager tests"""
import re
from datetime import datetime as dt

import pytest
from google.cloud.storage import Blob

from merino.jobs.wikipedia_indexer.filemanager import DirectoryParser, FileManager


@pytest.fixture
def mock_gcs_client(mocker):
    """Return a mock GCS Client instance"""
    return mocker.patch("merino.jobs.wikipedia_indexer.filemanager.Client").return_value


def test_directory_parser():
    """Test directory parser logic"""
    html_directory = """
    <a href="some_file.json" />
    <br />
    <a href="123.json" />
    <link src="something_else" />
    <a href="456.json" />
    """

    parser = DirectoryParser(re.compile("\\d+.json"))
    parser.feed(html_directory)

    assert len(parser.file_paths) == 2
    assert parser.file_paths[0] == "123.json"


@pytest.mark.usefixtures("mock_gcs_client")
@pytest.mark.parametrize(
    ["file_name", "expected_datetime"],
    [
        ("just-some-file.json", dt(1, 1, 1)),
        ("enwiki-20220101-cirrussearch-content.json.gz", dt(2022, 1, 1)),
        ("enwiki-19890101-cirrussearch-content.json.gz", dt(1989, 1, 1)),
        ("foo/bar/enwiki-19890101-cirrussearch-content.json.gz", dt(1989, 1, 1)),
        ("enwiki-20190132-cirrussearch-content.json.gz", dt(1, 1, 1)),
        ("enwiki-1234-cirrussearch-content.json.gz", dt(1, 1, 1)),
    ],
)
def test_parse_date(file_name, expected_datetime):
    """Test parse date regexp properly converts to a valid or sentinel datetime"""
    file_manager = FileManager("foo/bar", "a-project", "http://foo/")

    parsed_date = file_manager._parse_date(file_name)

    assert parsed_date == expected_datetime


@pytest.mark.usefixtures("mock_gcs_client")
@pytest.mark.parametrize(
    ["gcs_bucket", "expected_bucket", "expected_prefix"],
    [
        ("foo", "foo", ""),
        ("foo/bar", "foo", "bar"),
        ("foo/bar/baz", "foo", "bar/baz"),
    ],
)
def test_parse_gcs_bucket(gcs_bucket, expected_bucket, expected_prefix):
    """Test gcs bucket path parsing"""
    file_manager = FileManager(gcs_bucket, "a-project", "http://foo/")

    assert file_manager.gcs_bucket == expected_bucket
    assert file_manager.object_prefix == expected_prefix


@pytest.mark.usefixtures("mock_gcs_client")
@pytest.mark.parametrize(
    ["file_date", "gcs_date", "expected"],
    [
        (
            "20220101",
            "20210101",
            "http://test.com/enwiki-20220101-cirrussearch-content.json.gz",
        ),
        (
            "20210101",
            "20220101",
            None,
        ),
    ],
)
def test_get_latest_dump(requests_mock, file_date, gcs_date, expected):
    """Test directory parser and date comparisons of get_latest_dump"""
    base_url = "http://test.com"
    file_name = f"enwiki-{file_date}-cirrussearch-content.json.gz"
    latest_gcs = Blob(f"bar/enwiki-{gcs_date}-cirrussearch-content.json.gz", "foo")
    html_directory = f"<a href='{file_name}' />"
    requests_mock.get(base_url, text=html_directory)

    file_manager = FileManager("foo/bar", "a-project", base_url)

    latest_dump_url = file_manager.get_latest_dump(latest_gcs)

    assert latest_dump_url == expected


def test_get_latest_gcs(mock_gcs_client):
    """Test sorting logic for get_latest_gcs method"""
    blob1 = Blob("enwiki-20220101-cirrussearch-content.json.gz", "foo")
    blob2 = Blob("enwiki-20210101-cirrussearch-content.json.gz", "foo")

    mock_bucket = mock_gcs_client.bucket.return_value
    mock_bucket.list_blobs.return_value = [blob1, blob2]

    file_manager = FileManager("foo/bar", "a-project", "")
    latest_gcs = file_manager.get_latest_gcs()

    assert latest_gcs == blob1
