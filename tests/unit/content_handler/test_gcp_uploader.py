from logging import ERROR, INFO, LogRecord

import pytest
from pytest import LogCaptureFixture

from merino.content_handler.gcp_uploader import GcsUploader
from merino.content_handler.models import Image
from tests.types import FilterCaplogFixture


@pytest.fixture
def mock_gcs_client(mocker, mock_gcs_bucket):
    """Return a mock GCS Client instance"""
    mock_client = mocker.patch(
        "merino.content_handler.gcp_uploader.Client"
    ).return_value
    mock_client.get_bucket.return_value = mock_gcs_bucket
    return mock_client


@pytest.fixture
def mock_gcs_blob(mocker):
    """Return a mock GCS Blob instance"""
    return mocker.patch("merino.content_handler.gcp_uploader.Blob").return_value


@pytest.fixture
def mock_most_recent_gcs_blob(mocker):
    """Return a mock GCS Blob instance"""
    most_recent_blob = mocker.patch(
        "merino.content_handler.gcp_uploader.Blob"
    ).return_value
    most_recent_blob.name = "20220101120555_top_picks.json"
    return most_recent_blob


@pytest.fixture
def mock_gcs_bucket(mocker):
    """Return a mock GCS Bucket instance"""
    return mocker.patch("merino.content_handler.gcp_uploader.Bucket").return_value


@pytest.fixture
def test_https_cdn_host_name() -> str:
    return "https://test-cdn-host"


@pytest.fixture
def test_cdn_host_name() -> str:
    return "test-cdn-host"


@pytest.fixture
def test_destination_name() -> str:
    return "test-destination-name"


@pytest.fixture
def test_bucket_name() -> str:
    return "test-bucket-name"


@pytest.fixture
def test_image() -> Image:
    return Image(content=bytes(255), content_type="image/png")


def test_upload_image_with_non_https_cdn_host_name(
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
    mock_gcs_client,
    test_cdn_host_name,
    test_bucket_name,
    test_destination_name,
    test_image,
) -> None:
    """Test the upload_image method with the cdn_hostname class instance set to a non https value"""

    # set the logger level to the same in source method
    caplog.set_level(INFO)

    # creating the uploader object with cdn host name not containing "https"
    gcp_uploader = GcsUploader(mock_gcs_client, test_bucket_name, test_cdn_host_name)

    # force upload is set to FALSE by default
    result = gcp_uploader.upload_image(test_image, test_destination_name)

    # capture logger info output
    log_records: list[LogRecord] = filter_caplog(
        caplog.records, "merino.content_handler.gcp_uploader"
    )

    assert result == f"https://{test_cdn_host_name}/{test_destination_name}"
    # assert on logger calls
    assert len(log_records) == 1
    assert log_records[0].message.startswith(f"Content public url: {result}")


def test_upload_image_with_https_cdn_host_name(
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
    mock_gcs_client,
    test_https_cdn_host_name,
    test_bucket_name,
    test_destination_name,
    test_image,
) -> None:
    """Test the upload_image method with the cdn_hostname class instance set to a https value"""

    # set the logger level to the same in source method
    caplog.set_level(INFO)

    # creating the uploader object with cdn host name containing "https"
    gcp_uploader = GcsUploader(
        mock_gcs_client, test_bucket_name, test_https_cdn_host_name
    )

    # force upload is set to FALSE by default
    result = gcp_uploader.upload_image(test_image, test_destination_name)

    # capture logger info output
    log_records: list[LogRecord] = filter_caplog(
        caplog.records, "merino.content_handler.gcp_uploader"
    )

    assert result == f"{test_https_cdn_host_name}/{test_destination_name}"
    # assert on logger calls
    assert len(log_records) == 1
    assert log_records[0].message.startswith(f"Content public url: {result}")


def test_get_most_recent_file_with_two_files(
    mock_gcs_client,
    mock_gcs_bucket,
    mock_gcs_blob,
    mock_most_recent_gcs_blob,
    test_https_cdn_host_name,
    test_bucket_name,
) -> None:
    """Test the get_most_recent_file method with bucket returning two blobs/files"""

    mock_gcs_blob.name = "20210101120555_top_picks.json"
    # set the mock bucket's blob list to the two mocked blobs
    mock_gcs_bucket.list_blobs.return_value = [mock_most_recent_gcs_blob, mock_gcs_blob]

    gcp_uploader = GcsUploader(
        mock_gcs_client, test_bucket_name, test_https_cdn_host_name
    )

    excluded_file: str = "excluded.json"
    result = gcp_uploader.get_most_recent_file(
        exclusion=excluded_file, sort_key=lambda blob: blob.name
    )

    # result should be the the most recent blob / file
    assert result.name == mock_most_recent_gcs_blob.name


def test_get_most_recent_file_with_excluded_file(
    mock_gcs_client,
    mock_gcs_bucket,
    mock_gcs_blob,
    test_https_cdn_host_name,
    test_bucket_name,
) -> None:
    """Test the get_most_recent_file method with the mock bucket containing only the excluded blob/file"""

    excluded_file: str = "excluded.json"
    mock_gcs_blob.name = excluded_file

    # bucket only contains the excluded file
    mock_gcs_bucket.list_blobs.return_value = [mock_gcs_blob]

    gcp_uploader = GcsUploader(
        mock_gcs_client, test_bucket_name, test_https_cdn_host_name
    )

    # call the method with the exclusion argument set to the excluded file
    result = gcp_uploader.get_most_recent_file(
        exclusion=excluded_file, sort_key=lambda blob: blob.name
    )

    # result should be none since the bucket only contains the excluded file
    assert result is None


def test_upload_content_with_forced_upload_false_and_existing_blob(
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
    mock_gcs_client,
    mock_gcs_bucket,
    mock_gcs_blob,
    test_bucket_name,
    test_destination_name,
    test_https_cdn_host_name,
) -> None:
    """Test the upload_content method with default arguments"""

    # set the logger level to the same in source method
    caplog.set_level(INFO)

    mock_gcs_client.bucket.return_value = mock_gcs_bucket
    mock_gcs_bucket.blob.return_value = mock_gcs_blob

    gcp_uploader = GcsUploader(
        mock_gcs_client, test_bucket_name, test_https_cdn_host_name
    )
    content = bytes(255)

    # call the method
    result = gcp_uploader.upload_content(content, test_destination_name)

    # capture logger info output
    log_records: list[LogRecord] = filter_caplog(
        caplog.records, "merino.content_handler.gcp_uploader"
    )

    assert result == mock_gcs_blob
    assert len(log_records) == 0

    mock_gcs_blob.upload_from_string.assert_not_called()
    mock_gcs_blob.make_public.assert_not_called()


def test_upload_content_with_forced_upload_true_and_existing_blob(
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
    mock_gcs_client,
    mock_gcs_bucket,
    mock_gcs_blob,
    test_bucket_name,
    test_destination_name,
    test_https_cdn_host_name,
) -> None:
    """Test the upload_content method with forced_upload argument set to TRUE"""
    # set the logger level to the same in source method
    caplog.set_level(INFO)

    mock_gcs_client.bucket.return_value = mock_gcs_bucket
    mock_gcs_bucket.blob.return_value = mock_gcs_blob

    gcp_uploader = GcsUploader(
        mock_gcs_client, test_bucket_name, test_https_cdn_host_name
    )
    content = bytes(255)

    result = gcp_uploader.upload_content(
        content, test_destination_name, forced_upload=True
    )

    # capture logger info output
    log_records: list[LogRecord] = filter_caplog(
        caplog.records, "merino.content_handler.gcp_uploader"
    )

    assert result == mock_gcs_blob
    assert len(log_records) == 1
    assert log_records[0].message.startswith(f"Uploading blob: {mock_gcs_blob}")

    mock_gcs_blob.upload_from_string.assert_called_once_with(
        content, content_type="text/plain"
    )
    mock_gcs_blob.make_public.assert_called_once()


def test_upload_content_with_exception_thrown(
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
    mock_gcs_client,
    mock_gcs_bucket,
    mock_gcs_blob,
    test_bucket_name,
    test_destination_name,
    test_https_cdn_host_name,
) -> None:
    # set the logger level to ERROR for the exception
    caplog.set_level(ERROR)

    content = bytes(255)

    mock_gcs_client.bucket.return_value = mock_gcs_bucket
    mock_gcs_bucket.blob.return_value = mock_gcs_blob

    # make the blob.make_public() method throw a run time exception
    mock_gcs_blob.make_public.side_effect = RuntimeError("test-exception")

    gcp_uploader = GcsUploader(
        mock_gcs_client, test_bucket_name, test_https_cdn_host_name
    )

    # call the method
    gcp_uploader.upload_content(content, test_destination_name, forced_upload=True)

    # capture logger error output
    log_records: list[LogRecord] = filter_caplog(
        caplog.records, "merino.content_handler.gcp_uploader"
    )

    assert len(log_records) == 1
    assert log_records[0].message.startswith(
        f"Exception test-exception occurred while uploading {test_destination_name}"
    )
