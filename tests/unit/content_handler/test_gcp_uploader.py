from logging import INFO, LogRecord

import pytest
from pytest import LogCaptureFixture

from merino.content_handler.gcp_uploader import GcsUploader
from merino.content_handler.models import Image
from tests.types import FilterCaplogFixture


@pytest.fixture
def mock_gcs_client(mocker):
    """Return a mock GCS Client instance"""
    return mocker.patch("merino.content_handler.gcp_uploader.Client").return_value


@pytest.fixture
def mock_gcs_blob(mocker):
    """Return a mock GCS Blob instance"""
    return mocker.patch("merino.content_handler.gcp_uploader.Blob").return_value


@pytest.fixture
def mock_gcs_bucket(mocker):
    """Return a mock GCS Bucket instance"""
    return mocker.patch("merino.content_handler.gcp_uploader.Bucket").return_value


def test_upload_image_with_non_https_cdn_host_name(
    mock_gcs_client,
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
) -> None:
    """Test the upload_image method with the cdn_hostname class instance set to a non https value"""

    # test variables
    test_cdn_host_name = "test_cdn_host_name"
    test_bucket_name = "test_bucket_name"
    test_destination_name = "test-destination"
    test_image = Image(content=bytes(255), content_type="image/png")

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
    mock_gcs_client,
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
) -> None:
    """Test the upload_image method with the cdn_hostname class instance set to a https value"""

    # test variables
    test_https_cdn_host_name = "https://test-cdn-host"
    test_bucket_name = "test_bucket_name"
    test_destination_name = "test-destination"
    test_image = Image(content=bytes(255), content_type="image/png")

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


# def test_upload_content() -> None:
# 	# test goes here
#
#
#
# def test_get_most_recent_file() -> None:
# 	# test goes here
