"""Unit tests for local_mode.py module."""

from unittest.mock import patch
from datetime import datetime

from merino.jobs.navigational_suggestions.modes.local_mode_helpers import (
    LocalMetricsCollector,
    LocalDomainDataProvider,
)


@patch("pathlib.Path.mkdir")
def test_local_metrics_collector_init(mock_mkdir):
    """Test LocalMetricsCollector initialization."""
    # Test with default output directory
    collector = LocalMetricsCollector()
    assert collector.output_dir.name == "local_data"
    assert collector.domains_processed == 0
    assert collector.favicons_found == 0
    assert collector.urls_found == 0
    assert collector.titles_found == 0
    assert isinstance(collector.start_time, datetime)
    assert collector.domain_records == []
    mock_mkdir.assert_called_once_with(exist_ok=True, parents=True)

    # Test with custom output directory
    mock_mkdir.reset_mock()
    custom_collector = LocalMetricsCollector("/test/dir")
    assert custom_collector.output_dir.name == "dir"
    assert str(custom_collector.output_dir) == "/test/dir"
    mock_mkdir.assert_called_once_with(exist_ok=True, parents=True)


@patch("pathlib.Path.mkdir")
def test_record_domain_result(mock_mkdir):
    """Test record_domain_result method."""
    collector = LocalMetricsCollector()

    # Test with complete result
    complete_result = {
        "icon": "icon.png",
        "url": "https://example.com",
        "title": "Example",
        "domain": "example.com",
    }
    collector.record_domain_result("example.com", complete_result)

    assert collector.domains_processed == 1
    assert collector.favicons_found == 1
    assert collector.urls_found == 1
    assert collector.titles_found == 1
    assert len(collector.domain_records) == 1
    assert collector.domain_records[0]["domain"] == "example.com"
    assert collector.domain_records[0]["success"] is True

    # Test with partial result
    partial_result = {
        "url": "https://partial.com",
        "title": "Partial",
        "domain": "partial.com",
        "icon": None,
    }
    collector.record_domain_result("partial.com", partial_result)

    assert collector.domains_processed == 2
    assert collector.favicons_found == 1  # No change
    assert collector.urls_found == 2
    assert collector.titles_found == 2
    assert len(collector.domain_records) == 2
    assert collector.domain_records[1]["domain"] == "partial.com"
    assert collector.domain_records[1]["success"] is False


@patch("merino.jobs.navigational_suggestions.modes.local_mode_helpers.logger")
@patch("pathlib.Path.mkdir")
def test_log_progress(mock_mkdir, mock_logger):
    """Test _log_progress method."""
    collector = LocalMetricsCollector()
    collector.domains_processed = 20
    collector.favicons_found = 10

    # Set start_time to a fixed time in the past (5 seconds ago for a predictable rate)
    collector.start_time = datetime.now().timestamp() - 5
    collector.start_time = datetime.fromtimestamp(collector.start_time)

    # Call the method
    collector._log_progress()

    # Verify logger was called
    mock_logger.info.assert_called_once()
    log_message = mock_logger.info.call_args[0][0]
    assert "Progress: 20 domains processed" in log_message
    assert "Success rate: 50.0%" in log_message


def test_local_domain_data_provider_init():
    """Test LocalDomainDataProvider initialization."""
    custom_domains = ["example.com", "mozilla.org", "firefox.com"]

    # Test with default sample size
    provider = LocalDomainDataProvider(custom_domains)
    assert provider.custom_domains == custom_domains
    assert provider.sample_size == 50

    # Test with custom sample size
    custom_provider = LocalDomainDataProvider(custom_domains, sample_size=2)
    assert custom_provider.custom_domains == custom_domains
    assert custom_provider.sample_size == 2


@patch("merino.jobs.navigational_suggestions.modes.local_mode_helpers.logger")
def test_get_domain_data(mock_logger):
    """Test get_domain_data method."""
    custom_domains = ["example.com", "mozilla.org", "firefox.com"]

    # Test with sample size smaller than domains list
    provider = LocalDomainDataProvider(custom_domains, sample_size=2)
    domain_data = provider.get_domain_data()

    assert len(domain_data) == 2
    assert domain_data[0]["domain"] == "example.com"
    assert domain_data[0]["rank"] == 1
    assert domain_data[0]["origin"] == "https://example.com"
    assert domain_data[0]["suffix"] == "com"
    assert domain_data[0]["categories"] == ["Local_Testing"]
    assert domain_data[0]["source"] == "local-test"

    assert domain_data[1]["domain"] == "mozilla.org"
    assert domain_data[1]["rank"] == 2

    # Test with sample size larger than domains list
    provider = LocalDomainDataProvider(custom_domains, sample_size=10)
    domain_data = provider.get_domain_data()

    assert len(domain_data) == 3  # Only 3 domains available
    assert domain_data[2]["domain"] == "firefox.com"
    assert domain_data[2]["rank"] == 3

    # Verify logging
    mock_logger.info.assert_called()
    log_calls = mock_logger.info.call_args_list
    assert any("Generated" in str(call) for call in log_calls)
    assert any("Sample range" in str(call) for call in log_calls)


@patch("merino.jobs.navigational_suggestions.modes.local_mode_helpers.logger")
def test_get_domain_data_empty_list(mock_logger):
    """Test get_domain_data with an empty domains list."""
    provider = LocalDomainDataProvider([], sample_size=5)
    domain_data = provider.get_domain_data()

    assert len(domain_data) == 0
    mock_logger.info.assert_called()


@patch("merino.jobs.navigational_suggestions.modes.local_mode_helpers.logger")
@patch("builtins.open")
@patch("json.dump")
@patch("pathlib.Path.mkdir")
def test_save_report(mock_mkdir, mock_json_dump, mock_open, mock_logger):
    """Test save_report method."""
    collector = LocalMetricsCollector("/test/dir")
    collector.domains_processed = 100
    collector.favicons_found = 75
    collector.urls_found = 80
    collector.titles_found = 90
    collector.domain_records = [
        {
            "domain": "example.com",
            "success": True,
            "url": "https://example.com",
            "title": "Example",
        }
    ]

    # Set start_time to a fixed time in the past
    collector.start_time = datetime.now()

    # Call the method
    collector.save_report()

    # Verify json.dump was called
    mock_json_dump.assert_called_once()
    report_data = mock_json_dump.call_args[0][0]

    # Verify report data
    assert report_data["total_domains"] == 100
    assert report_data["favicons_found"] == 75
    assert report_data["favicon_success_rate"] == 0.75
    assert report_data["urls_found"] == 80
    assert report_data["url_success_rate"] == 0.8
    assert report_data["titles_found"] == 90
    assert report_data["title_success_rate"] == 0.9
    assert "elapsed_seconds" in report_data
    assert "processing_rate" in report_data
    assert "timestamp" in report_data
    assert len(report_data["domains"]) == 1

    # Verify logger calls for summary
    assert mock_logger.info.call_count >= 8  # At least 8 log lines for summary
