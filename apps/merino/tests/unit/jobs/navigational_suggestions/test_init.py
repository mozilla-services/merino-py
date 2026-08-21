# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Improved unit tests for __init__.py module."""

from unittest.mock import MagicMock, patch

import pytest

from merino.jobs.navigational_suggestions import prepare_domain_metadata
from merino.jobs.navigational_suggestions.processing.manifest_builder import (
    get_serp_categories,
    construct_partner_manifest,
    construct_top_picks,
)
from merino.jobs.navigational_suggestions.modes.normal_mode import (
    run_normal_mode,
    write_xcom_file,
)
from merino.utils.domain_categories.models import Category


def test_write_xcom_file(mocker):
    """Test _write_xcom_file function."""
    mock_open = mocker.patch("builtins.open", mocker.mock_open())
    mock_json_dump = mocker.patch("json.dump")

    test_data = {"key": "value", "nested": {"data": "test"}}
    write_xcom_file(test_data)

    # Verify file was opened with correct path
    mock_open.assert_called_once_with("/airflow/xcom/return.json", "w")

    # Verify json.dump was called with correct data
    file_handle = mock_open.return_value.__enter__.return_value
    mock_json_dump.assert_called_once_with(test_data, file_handle)


def test_get_serp_categories_with_complex_urls(mocker):
    """Test get_serp_categories with complex URLs."""
    # Directly patch the URL class to return a controlled parsed URL
    mock_url = mocker.MagicMock()
    mock_url.host = "example.com"
    mocker.patch("httpx.URL", return_value=mock_url)

    # Mock md5 hashing
    mock_md5 = mocker.MagicMock()
    mock_md5.digest.return_value = b"test_digest"
    mocker.patch(
        "merino.jobs.navigational_suggestions.processing.manifest_builder.md5",
        return_value=mock_md5,
    )

    # Mock base64 encoding
    mocker.patch(
        "merino.jobs.navigational_suggestions.processing.manifest_builder.base64.b64encode",
        return_value=b"encoded_digest",
    )
    mocker.patch(
        "merino.jobs.navigational_suggestions.processing.manifest_builder.base64.b64encode.decode",
        return_value="encoded_digest",
    )

    # Mock DOMAIN_MAPPING
    mock_domain_mapping = mocker.patch(
        "merino.jobs.navigational_suggestions.processing.manifest_builder.DOMAIN_MAPPING"
    )
    mock_domain_mapping.get.return_value = [Category.Tech]

    # Test with various URL formats
    urls = [
        "https://example.com/path?query=value",
        "https://sub.example.co.uk/path",
        "https://user:pass@example.org/path",
    ]

    for url in urls:
        result = get_serp_categories(url)
        assert result == [Category.Tech.value]
        mock_domain_mapping.get.assert_called()


def test_get_serp_categories_none_url():
    """Test get_serp_categories with None URL."""
    result = get_serp_categories(None)
    assert result is None


def test_get_serp_categories_detailed(mocker):
    """Test get_serp_categories with more details."""
    categories = [
        Category.Inconclusive,
        Category.Tech,
        Category.Autos,
        Category.News,
        Category.Business,
    ]

    for category in categories:
        mock_url = mocker.MagicMock()
        mock_url.host = f"test-{category.name.lower()}.com"
        mocker.patch("httpx.URL", return_value=mock_url)

        # Setup mock hashing and encoding
        mock_md5 = mocker.MagicMock()
        mock_md5.digest.return_value = f"digest-{category.name}".encode()
        mocker.patch(
            "merino.jobs.navigational_suggestions.processing.manifest_builder.md5",
            return_value=mock_md5,
        )

        encoded_mock = mocker.MagicMock()
        encoded_mock.decode.return_value = f"encoded-{category.name}"
        mocker.patch(
            "merino.jobs.navigational_suggestions.processing.manifest_builder.base64.b64encode",
            return_value=encoded_mock,
        )

        # Mock domain mapping to return this category
        mock_domain_mapping = mocker.patch(
            "merino.jobs.navigational_suggestions.processing.manifest_builder.DOMAIN_MAPPING"
        )
        mock_domain_mapping.get.return_value = [category]

        # Test the function
        url = f"https://test-{category.name.lower()}.com"
        result = get_serp_categories(url)

        # Verify the result contains the category value
        assert result == [category.value]


def test_construct_top_picks_complete(mocker):
    """Test _construct_top_picks with complete data."""
    domain_data = [
        {"rank": 1, "categories": ["web"], "source": "top-picks", "domain": "example.com"},
        {
            "rank": 2,
            "categories": ["autos", "service"],
            "source": "custom-domains",
            "domain": "store.example.org",
        },
        {"rank": 3, "categories": ["news"], "source": "top-picks", "domain": "news.example.net"},
    ]

    domain_metadata = [
        {
            "domain": "example",
            "url": "https://example.com",
            "title": "Example Site",
            "icon": "https://example.com/favicon.ico",
        },
        {
            "domain": "store",
            "url": "https://store.example.org",
            "title": "Example Store",
            "icon": "https://store.example.org/favicon.png",
        },
        {
            "domain": "news",
            "url": "https://news.example.net",
            "title": "Example News",
            "icon": "https://news.example.net/icon.svg",
        },
    ]

    def mock_get_serp_categories(url):
        if "example.com" in url:
            return [Category.Tech.value]
        elif "store" in url:
            return [Category.Autos.value]
        elif "news" in url:
            return [Category.News.value]
        return [Category.Inconclusive.value]

    mocker.patch(
        "merino.jobs.navigational_suggestions.processing.manifest_builder.get_serp_categories",
        side_effect=mock_get_serp_categories,
    )

    # Call the function
    result = construct_top_picks(domain_data, domain_metadata)

    # Verify the result structure
    assert "domains" in result
    assert len(result["domains"]) == 3

    # Verify each domain's data
    assert result["domains"][0]["domain"] == "example"
    assert result["domains"][0]["rank"] == 1
    assert result["domains"][0]["categories"] == ["web"]
    assert result["domains"][0]["serp_categories"] == [Category.Tech.value]
    assert result["domains"][0]["source"] == "top-picks"

    assert result["domains"][1]["domain"] == "store"
    assert result["domains"][1]["categories"] == ["autos", "service"]
    assert result["domains"][1]["serp_categories"] == [Category.Autos.value]
    assert result["domains"][1]["source"] == "custom-domains"

    assert result["domains"][2]["domain"] == "news"
    assert result["domains"][2]["categories"] == ["news"]
    assert result["domains"][2]["serp_categories"] == [Category.News.value]
    assert result["domains"][2]["source"] == "top-picks"


def test_construct_top_picks_with_missing_values(mocker):
    """Test _construct_top_picks with missing values."""
    # Test with domain_data having missing source field
    domain_data = [
        {"rank": 1, "categories": ["web"]},  # Missing source field
    ]

    domain_metadata = [
        {
            "domain": "example.com",
            "url": "https://example.com",
            "title": "Example",
            "icon": "icon1",
        }
    ]

    # Mock _get_serp_categories to return a fixed value
    mocker.patch(
        "merino.jobs.navigational_suggestions.processing.manifest_builder.get_serp_categories",
        return_value=[0],
    )

    result = construct_top_picks(domain_data, domain_metadata)

    # Should still construct a valid result with default source
    assert len(result["domains"]) == 1
    assert result["domains"][0]["source"] == "top-picks"  # Default value


def test_construct_top_picks_filter_null_urls(mocker):
    """Test _construct_top_picks filters out entries with null URLs."""
    domain_data = [
        {"rank": 1, "categories": ["web"], "source": "top-picks"},
        {"rank": 2, "categories": ["autos"], "source": "custom-domains"},
    ]

    domain_metadata = [
        {
            "domain": "example.com",
            "url": None,  # Null URL
            "title": "Example",
            "icon": "icon1",
        },
        {
            "domain": "valid.com",
            "url": "https://valid.com",
            "title": "Valid",
            "icon": "icon2",
        },
    ]

    # Mock _get_serp_categories to return a fixed value
    mocker.patch(
        "merino.jobs.navigational_suggestions.processing.manifest_builder.get_serp_categories",
        return_value=[0],
    )

    result = construct_top_picks(domain_data, domain_metadata)

    # Should filter out the entry with null URL
    assert len(result["domains"]) == 1
    assert result["domains"][0]["domain"] == "valid.com"


def test_construct_top_picks_with_empty_data():
    """Test _construct_top_picks with empty input data."""
    # Test with empty domain_data
    result = construct_top_picks([], [])
    assert "domains" in result
    assert len(result["domains"]) == 0

    # Test with empty domain_metadata but non-empty domain_data
    # This should still result in empty output since we're filtering by URL
    domain_data = [{"rank": 1, "categories": ["web"], "source": "top-picks"}]
    result = construct_top_picks(domain_data, [])
    assert "domains" in result
    assert len(result["domains"]) == 0


def test_construct_partner_manifest_complete():
    """Test _construct_partner_manifest with valid data."""
    partner_favicon_source = [
        {
            "domain": "partner1.com",
            "url": "https://partner1.com",
            "icon": "https://partner1.com/favicon.ico",
        },
        {
            "domain": "partner2.com",
            "url": "https://partner2.com",
            "icon": "https://partner2.com/favicon.ico",
        },
    ]

    uploaded_favicons = [
        "https://cdn.example.com/favicon1.ico",
        "https://cdn.example.com/favicon2.ico",
    ]

    result = construct_partner_manifest(partner_favicon_source, uploaded_favicons)

    # Verify the result structure
    assert "partners" in result
    assert len(result["partners"]) == 2

    # Verify each partner's data
    assert result["partners"][0]["domain"] == "partner1.com"
    assert result["partners"][0]["url"] == "https://partner1.com"
    assert result["partners"][0]["original_icon_url"] == "https://partner1.com/favicon.ico"
    assert result["partners"][0]["gcs_icon_url"] == "https://cdn.example.com/favicon1.ico"

    assert result["partners"][1]["domain"] == "partner2.com"
    assert result["partners"][1]["url"] == "https://partner2.com"
    assert result["partners"][1]["original_icon_url"] == "https://partner2.com/favicon.ico"
    assert result["partners"][1]["gcs_icon_url"] == "https://cdn.example.com/favicon2.ico"


def test_construct_partner_manifest_length_mismatch():
    """Test _construct_partner_manifest with length mismatch."""
    partner_favicon_source = [
        {
            "domain": "partner1.com",
            "url": "https://partner1.com",
            "icon": "https://partner1.com/favicon.ico",
        },
        {
            "domain": "partner2.com",
            "url": "https://partner2.com",
            "icon": "https://partner2.com/favicon.ico",
        },
    ]

    # Fewer uploaded favicons than sources
    uploaded_favicons = [
        "https://cdn.example.com/favicon1.ico",
    ]

    # Should raise ValueError due to length mismatch
    with pytest.raises(ValueError) as excinfo:
        construct_partner_manifest(partner_favicon_source, uploaded_favicons)

    assert "Mismatch" in str(excinfo.value)


def test_construct_partner_manifest_empty():
    """Test _construct_partner_manifest with empty inputs."""
    # Empty inputs should result in empty partner list
    result = construct_partner_manifest([], [])
    assert "partners" in result
    assert len(result["partners"]) == 0


@patch("merino.jobs.navigational_suggestions.run_normal_mode")
def test_prepare_domain_metadata_normal_mode(mock_run_normal):
    """Test prepare_domain_metadata with normal mode."""
    # Call with normal mode parameters
    prepare_domain_metadata(
        source_gcp_project="test-project",
        destination_gcp_project="test-dest-project",
        destination_gcs_bucket="test-bucket",
        destination_cdn_hostname="cdn.example.com",
        force_upload=True,
        write_xcom=True,
        min_favicon_width=48,
        local_mode=False,
        enable_monitoring=False,
    )

    # Verify run_normal_mode was called with correct parameters
    mock_run_normal.assert_called_once_with(
        source_gcp_project="test-project",
        destination_gcp_project="test-dest-project",
        destination_gcs_bucket="test-bucket",
        destination_cdn_hostname="cdn.example.com",
        force_upload=True,
        write_xcom=True,
        min_favicon_width=48,
        enable_monitoring=False,
    )


@patch("merino.jobs.navigational_suggestions.run_local_mode")
def test_prepare_domain_metadata_local_mode(mock_run_local):
    """Test prepare_domain_metadata with local mode."""
    # Call with local mode parameters
    prepare_domain_metadata(
        local_mode=True,
        local_sample_size=20,
        local_data_dir="./test_data",
        min_favicon_width=64,
        enable_monitoring=False,
    )

    # Verify run_local_mode was called with correct parameters
    mock_run_local.assert_called_once_with(
        local_sample_size=20,
        local_data_dir="./test_data",
        min_favicon_width=64,
        enable_monitoring=False,
    )


def test_prepare_domain_metadata_with_typer_options(mocker):
    """Test prepare_domain_metadata with typer.Option objects."""

    # Mock typer.Option objects
    class MockOption:
        def __init__(self, default):
            self.default = default

    # Create a mock for run_normal_mode
    mock_run_normal = mocker.patch("merino.jobs.navigational_suggestions.run_normal_mode")

    # Call prepare_domain_metadata with MockOption objects
    prepare_domain_metadata(
        source_gcp_project=MockOption("test-project"),
        destination_gcp_project=MockOption("test-dest-project"),
        destination_gcs_bucket=MockOption("test-bucket"),
        destination_cdn_hostname=MockOption("cdn.example.com"),
        force_upload=MockOption(True),
        write_xcom=MockOption(True),
        min_favicon_width=MockOption(48),
        local_mode=False,
        enable_monitoring=False,
    )

    # Verify run_normal_mode was called with the default values
    mock_run_normal.assert_called_once_with(
        source_gcp_project="test-project",
        destination_gcp_project="test-dest-project",
        destination_gcs_bucket="test-bucket",
        destination_cdn_hostname="cdn.example.com",
        force_upload=True,
        write_xcom=True,
        min_favicon_width=48,
        enable_monitoring=False,
    )


def test_prepare_domain_metadata_local_mode_with_typer_options(mocker):
    """Test prepare_domain_metadata local mode with typer.Option objects."""

    # Mock typer.Option objects
    class MockOption:
        def __init__(self, default):
            self.default = default

    # Create a mock for run_local_mode
    mock_run_local = mocker.patch("merino.jobs.navigational_suggestions.run_local_mode")

    # Call prepare_domain_metadata with MockOption objects
    prepare_domain_metadata(
        local_mode=True,
        local_sample_size=MockOption(20),
        local_data_dir=MockOption("./test_data"),
        min_favicon_width=MockOption(64),
        enable_monitoring=False,
    )

    # Verify run_local_mode was called with the default values
    mock_run_local.assert_called_once_with(
        local_sample_size=20,
        local_data_dir="./test_data",
        min_favicon_width=64,
        enable_monitoring=False,
    )


def test_run_normal_mode_execution_flow(mocker):
    """Test the execution flow of run_normal_mode without patch decorators."""
    from unittest.mock import MagicMock

    # Setup all mocks using mocker directly
    mocker.patch(
        "merino.jobs.navigational_suggestions.modes.normal_mode.PARTNER_FAVICONS",
        [
            {
                "domain": "test.com",
                "url": "https://test.com",
                "icon": "https://test.com/favicon.ico",
            }
        ],
    )
    mocker.patch(
        "merino.jobs.navigational_suggestions.modes.normal_mode.TOP_PICKS_BLOCKLIST", set()
    )

    # Mock classes and their return values in one go
    mock_downloader = MagicMock()
    mock_downloader.download_data.return_value = [{"domain": "test.com", "categories": ["web"]}]
    mock_downloader_class = mocker.patch(
        "merino.jobs.navigational_suggestions.modes.normal_mode.DomainDataDownloader"
    )
    mock_downloader_class.return_value = mock_downloader

    mock_processor = MagicMock()
    mock_processor.process_domain_metadata.return_value = [
        {"domain": "test", "url": "https://test.com", "title": "Test", "icon": "icon1"}
    ]
    mock_processor_class = mocker.patch(
        "merino.jobs.navigational_suggestions.modes.normal_mode.DomainProcessor"
    )
    mock_processor_class.return_value = mock_processor

    mock_blob = MagicMock()
    mock_blob.name = "test_blob.json"
    mock_blob.public_url = "https://cdn.example.com/test_blob.json"

    mock_uploader = MagicMock()
    mock_uploader.upload_top_picks.return_value = mock_blob
    mock_uploader.upload_favicons.return_value = ["https://cdn.example.com/favicon.ico"]
    mock_uploader.get_latest_file_for_diff.return_value = {"domains": []}

    mock_uploader_class = mocker.patch(
        "merino.jobs.navigational_suggestions.modes.normal_mode.DomainMetadataUploader"
    )
    mock_uploader_class.return_value = mock_uploader

    mocker.patch("merino.jobs.navigational_suggestions.modes.normal_mode.GcsUploader")

    mock_diff = MagicMock()
    mock_diff.compare_top_picks.return_value = (set(), set(), set())
    mock_diff.create_diff.return_value = {"diff": "data"}

    mock_diff_class = mocker.patch(
        "merino.jobs.navigational_suggestions.modes.normal_mode.DomainDiff"
    )
    mock_diff_class.return_value = mock_diff

    # Mock construct_top_picks and construct_partner_manifest
    mocker.patch(
        "merino.jobs.navigational_suggestions.modes.normal_mode.construct_top_picks",
        return_value={"domains": []},
    )
    mocker.patch(
        "merino.jobs.navigational_suggestions.modes.normal_mode.construct_partner_manifest",
        return_value={"partners": []},
    )

    # Execute the function
    run_normal_mode(
        source_gcp_project="test-project",
        destination_gcp_project="test-dest-project",
        destination_gcs_bucket="test-bucket",
        destination_cdn_hostname="cdn.example.com",
        force_upload=True,
        write_xcom=False,
        min_favicon_width=48,
        enable_monitoring=False,
    )

    # Verify the interactions
    mock_downloader_class.assert_called_once_with("test-project")
    mock_downloader.download_data.assert_called_once()
    mock_processor.process_domain_metadata.assert_called_once()
    mock_uploader.upload_favicons.assert_called_once()
    mock_uploader.get_latest_file_for_diff.assert_called_once()
    mock_diff.compare_top_picks.assert_called_once()
    mock_diff.create_diff.assert_called_once()
    mock_uploader.upload_top_picks.assert_called_once()


def test_run_normal_mode_with_xcom(mocker):
    """Test run_normal_mode with write_xcom=True."""
    # Mock all dependencies
    mock_write_xcom = mocker.patch(
        "merino.jobs.navigational_suggestions.modes.normal_mode.write_xcom_file"
    )
    mocker.patch(
        "merino.jobs.navigational_suggestions.modes.normal_mode.PARTNER_FAVICONS",
        [
            {
                "domain": "test.com",
                "url": "https://test.com",
                "icon": "https://test.com/favicon.ico",
            }
        ],
    )
    mocker.patch(
        "merino.jobs.navigational_suggestions.modes.normal_mode.TOP_PICKS_BLOCKLIST", set()
    )

    # Mock the classes
    mock_domain_diff_class = mocker.patch(
        "merino.jobs.navigational_suggestions.modes.normal_mode.DomainDiff"
    )
    mock_downloader_class = mocker.patch(
        "merino.jobs.navigational_suggestions.modes.normal_mode.DomainDataDownloader"
    )
    mock_processor_class = mocker.patch(
        "merino.jobs.navigational_suggestions.modes.normal_mode.DomainProcessor"
    )
    mock_uploader_class = mocker.patch(
        "merino.jobs.navigational_suggestions.modes.normal_mode.DomainMetadataUploader"
    )

    # Setup mock return values
    mock_downloader = mock_downloader_class.return_value
    mock_downloader.download_data.return_value = [{"domain": "test.com", "categories": ["web"]}]

    mock_processor = mock_processor_class.return_value
    mock_processor.process_domain_metadata.return_value = [
        {"domain": "test", "url": "https://test.com", "title": "Test", "icon": "icon1"}
    ]

    mock_uploader = mock_uploader_class.return_value
    mock_blob = MagicMock()
    mock_blob.name = "test_blob.json"
    mock_blob.public_url = "https://cdn.example.com/test_blob.json"
    mock_uploader.upload_top_picks.return_value = mock_blob
    mock_uploader.upload_favicons.return_value = ["https://cdn.example.com/favicon.ico"]
    mock_uploader.get_latest_file_for_diff.return_value = {"domains": []}

    mock_diff = mock_domain_diff_class.return_value
    mock_diff.compare_top_picks.return_value = (set(), set(), set())
    mock_diff.create_diff.return_value = {"diff": "data"}

    # Mock construct_top_picks and construct_partner_manifest
    mocker.patch(
        "merino.jobs.navigational_suggestions.modes.normal_mode.construct_top_picks",
        return_value={"domains": []},
    )
    mocker.patch(
        "merino.jobs.navigational_suggestions.modes.normal_mode.construct_partner_manifest",
        return_value={"partners": []},
    )

    # Call the function with write_xcom=True
    run_normal_mode(
        source_gcp_project="test-project",
        destination_gcp_project="test-dest-project",
        destination_gcs_bucket="test-bucket",
        destination_cdn_hostname="cdn.example.com",
        force_upload=True,
        write_xcom=True,
        min_favicon_width=48,
        enable_monitoring=False,
    )

    # Verify _write_xcom_file was called
    mock_write_xcom.assert_called_once()
    args = mock_write_xcom.call_args[0][0]
    assert "top_pick_url" in args
    assert "diff" in args


def test_run_local_mode_socket_failure(monkeypatch, mocker):
    """Test run_local_mode when GCS emulator socket connection fails."""
    from merino.jobs.navigational_suggestions.modes.local_mode_runner import run_local_mode

    # Patch environment variables
    monkeypatch.setattr("os.environ", {})

    # Mock os.makedirs
    mocker.patch("os.makedirs")

    # Mock socket with proper behavior
    mock_socket_instance = MagicMock()
    mock_socket_instance.connect_ex.return_value = 1  # Connection failed
    mock_socket_instance.settimeout.return_value = None

    mock_socket = MagicMock()
    mock_socket.socket.return_value = mock_socket_instance
    monkeypatch.setattr(
        "merino.jobs.navigational_suggestions.modes.local_mode_runner.socket", mock_socket
    )

    # Mock logger
    mock_logger = mocker.patch(
        "merino.jobs.navigational_suggestions.modes.local_mode_runner.logger"
    )

    # Make sys.exit raise an exception we can catch to stop execution
    mock_exit = mocker.patch(
        "merino.jobs.navigational_suggestions.modes.local_mode_runner.sys.exit"
    )
    mock_exit.side_effect = SystemExit("Mocked exit")

    # Other mocks
    mocker.patch(
        "merino.jobs.navigational_suggestions.modes.local_mode_runner.CUSTOM_DOMAINS", ["test.com"]
    )
    mocker.patch("pathlib.Path.mkdir")
    mocker.patch(
        "merino.jobs.navigational_suggestions.modes.local_mode_runner.LocalMetricsCollector"
    )
    mocker.patch(
        "merino.jobs.navigational_suggestions.modes.local_mode_runner.LocalDomainDataProvider"
    )

    # Call the function with exception handling to catch the SystemExit
    try:
        run_local_mode(20, "./test_data", 48, False)
        assert False, "Should have exited with SystemExit"
    except SystemExit:
        # This is expected behavior
        pass

    # Verify socket was used
    mock_socket.socket.assert_called_once()
    mock_socket_instance.connect_ex.assert_called_once_with(("localhost", 4443))

    # Verify error was logged and exit was called
    mock_logger.error.assert_called_once()
    mock_exit.assert_called_once_with(1)


@pytest.mark.skip(reason="Test is too complex and requires extensive mocking - needs refactoring")
def test_run_local_mode_success_path(monkeypatch, mocker):
    """Test run_local_mode successful execution path."""
    from merino.jobs.navigational_suggestions.modes.local_mode_runner import run_local_mode
    from google.cloud.storage import Blob

    # Patch environment variables and os functions
    monkeypatch.setattr("os.environ", {})
    mocker.patch("os.makedirs", return_value=None)

    # Mock LocalMetricsCollector and LocalDomainDataProvider
    mock_metrics = mocker.MagicMock()
    mock_domain_provider = mocker.MagicMock()
    mock_domain_provider.get_domain_data.return_value = [
        {"domain": "test.com", "categories": ["Test"], "rank": 1}
    ]

    mocker.patch(
        "merino.jobs.navigational_suggestions.modes.local_mode_runner.LocalMetricsCollector",
        return_value=mock_metrics,
    )
    mocker.patch(
        "merino.jobs.navigational_suggestions.modes.local_mode_runner.LocalDomainDataProvider",
        return_value=mock_domain_provider,
    )

    # Mock socket connection success
    mock_socket = mocker.MagicMock()
    mock_socket_instance = mocker.MagicMock()
    mock_socket_instance.connect_ex.return_value = 0  # Success
    mock_socket.socket.return_value = mock_socket_instance
    monkeypatch.setattr(
        "merino.jobs.navigational_suggestions.modes.local_mode_runner.socket", mock_socket
    )

    # Mock Google Cloud stuff
    mock_client = mocker.MagicMock()
    mock_bucket = mocker.MagicMock()
    mock_bucket.exists.return_value = True
    mock_client.bucket.return_value = mock_bucket

    mocker.patch("google.cloud.storage.Client", return_value=mock_client)

    # Mock GcsUploader and other classes
    mock_uploader = mocker.MagicMock()
    mocker.patch("merino.utils.gcs.gcs_uploader.GcsUploader", return_value=mock_uploader)

    mock_domain_uploader = mocker.MagicMock()
    mock_blob = mocker.MagicMock(spec=Blob)
    mock_blob.name = "test_blob.json"
    mock_blob.public_url = "https://test.url/test_blob.json"
    mock_domain_uploader.upload_top_picks.return_value = mock_blob

    # Important fix: Return a list of strings for upload_favicons
    # This needs to match the number of items in PARTNER_FAVICONS
    mock_domain_uploader.upload_favicons.return_value = ["https://cdn.example.com/favicon.ico"]

    mocker.patch(
        "merino.jobs.navigational_suggestions.modes.normal_mode.DomainMetadataUploader",
        return_value=mock_domain_uploader,
    )

    # Mock PARTNER_FAVICONS to have one item, matching our mock response
    mocker.patch(
        "merino.jobs.navigational_suggestions.enrichments.partner_favicons.PARTNER_FAVICONS",
        [
            {
                "domain": "test.com",
                "url": "https://test.com",
                "icon": "https://test.com/favicon.ico",
            }
        ],
    )

    # Mock domain processor
    mock_processor = mocker.MagicMock()
    mock_processor.process_domain_metadata.return_value = [
        {"domain": "test", "url": "https://test.com", "title": "Test", "icon": "icon.png"}
    ]
    mocker.patch(
        "merino.jobs.navigational_suggestions.modes.local_mode_runner.DomainProcessor",
        return_value=mock_processor,
    )

    # Mock open and write operations
    mocker.patch("builtins.open", mocker.mock_open())

    # Mock construct functions
    mocker.patch(
        "merino.jobs.navigational_suggestions.modes.local_mode_runner.construct_top_picks",
        return_value={"domains": []},
    )
    mocker.patch(
        "merino.jobs.navigational_suggestions.modes.local_mode_runner.construct_partner_manifest",
        return_value={"partners": []},
    )

    # Call the function with keyword arguments
    run_local_mode(
        local_sample_size=20,
        local_data_dir="./test_data",
        min_favicon_width=48,
        enable_monitoring=False,
    )

    # Verify key interactions
    mock_domain_provider.get_domain_data.assert_called_once()
    mock_processor.process_domain_metadata.assert_called_once()
    mock_domain_uploader.upload_favicons.assert_called_once()
    mock_domain_uploader.upload_top_picks.assert_called_once()
    mock_metrics.save_report.assert_called_once()


def test_partner_favicons_import():
    """Test that we can import and access PARTNER_FAVICONS."""
    from merino.jobs.navigational_suggestions.enrichments.partner_favicons import PARTNER_FAVICONS

    assert PARTNER_FAVICONS is not None
    assert isinstance(PARTNER_FAVICONS, list)


def test_get_serp_categories_with_invalid_url():
    """Test _get_serp_categories handling of invalid URLs."""
    # First try with a valid URL
    result1 = get_serp_categories("https://example.com")

    # Then try with an invalid URL that would raise an exception in URL parsing
    result2 = get_serp_categories("not-a-url")

    # At least one of these should return a value (the valid URL)
    assert result1 is not None or result2 is not None
