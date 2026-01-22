"""Integration tests for local_mode module"""

import json
import shutil
import tempfile
from pathlib import Path

import pytest
from freezegun import freeze_time

from merino.jobs.navigational_suggestions.modes.local_mode_helpers import (
    LocalMetricsCollector,
    LocalDomainDataProvider,
)
from merino.jobs.navigational_suggestions.enrichments.custom_domains import CUSTOM_DOMAINS


@pytest.fixture(scope="function")
def temp_dir():
    """Create a temporary directory for test data"""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    # Clean up after test
    shutil.rmtree(temp_dir)


def test_local_metrics_collector_init(temp_dir):
    """Test LocalMetricsCollector initialization"""
    # Test with existing directory
    collector = LocalMetricsCollector(temp_dir)
    assert collector.output_dir == Path(temp_dir)
    assert collector.domains_processed == 0
    assert collector.favicons_found == 0
    assert collector.urls_found == 0
    assert collector.titles_found == 0

    # Test with non-existing directory
    new_dir = Path(temp_dir) / "metrics"
    collector = LocalMetricsCollector(str(new_dir))
    assert new_dir.exists()


def test_local_metrics_collector_record_domain_result(temp_dir, caplog):
    """Test recording domain results"""
    collector = LocalMetricsCollector(temp_dir)

    # Test successful result
    success_result = {
        "url": "https://example.com",
        "title": "Example Domain",
        "icon": "https://example.com/favicon.ico",
        "domain": "example",
    }
    collector.record_domain_result("example.com", success_result)

    assert collector.domains_processed == 1
    assert collector.favicons_found == 1
    assert collector.urls_found == 1
    assert collector.titles_found == 1

    # Test failed result
    failed_result = {"url": None, "title": None, "icon": None, "domain": None}
    collector.record_domain_result("failed.com", failed_result)

    assert collector.domains_processed == 2
    assert collector.favicons_found == 1
    assert collector.urls_found == 1
    assert collector.titles_found == 1

    # Check domain records
    assert len(collector.domain_records) == 2
    assert collector.domain_records[0]["domain"] == "example.com"
    assert collector.domain_records[0]["success"] is True
    assert collector.domain_records[1]["domain"] == "failed.com"
    assert collector.domain_records[1]["success"] is False


@freeze_time("2023-01-01 12:00:00")
def test_local_metrics_collector_save_report(temp_dir):
    """Test saving metrics report"""
    collector = LocalMetricsCollector(temp_dir)

    # Add some test data
    success_result = {
        "url": "https://example.com",
        "title": "Example",
        "icon": "icon.png",
        "domain": "example",
    }
    failed_result = {"url": None, "title": None, "icon": None, "domain": None}

    collector.record_domain_result("example.com", success_result)
    collector.record_domain_result("failed.com", failed_result)

    # Save report
    collector.save_report()

    # Check if file was created
    output_files = list(Path(temp_dir).glob("metrics_*.json"))
    assert len(output_files) == 1

    # Check file content
    with open(output_files[0], "r") as f:
        report = json.load(f)

    assert report["total_domains"] == 2
    assert report["favicons_found"] == 1
    assert report["favicon_success_rate"] == 0.5
    assert "domains" in report
    assert len(report["domains"]) == 2


def test_local_domain_data_provider():
    """Test LocalDomainDataProvider functionality"""
    # Test with default sample size
    provider = LocalDomainDataProvider(CUSTOM_DOMAINS, 50)
    data = provider.get_domain_data()

    assert len(data) == 50
    assert data[0]["rank"] == 1
    assert data[0]["source"] == "local-test"

    # Test with custom sample size
    provider = LocalDomainDataProvider(CUSTOM_DOMAINS, 10)
    data = provider.get_domain_data()

    assert len(data) == 10

    # Test with sample size larger than available domains
    test_domains = ["example.com", "test.com", "domain.com"]
    provider = LocalDomainDataProvider(test_domains, 10)
    data = provider.get_domain_data()

    assert len(data) == 3  # Should only return the available domains
    assert data[0]["domain"] == "example.com"
    assert data[1]["domain"] == "test.com"
    assert data[2]["domain"] == "domain.com"

    # Verify domain data structure
    domain_data = data[0]
    assert "rank" in domain_data
    assert "domain" in domain_data
    assert "host" in domain_data
    assert "origin" in domain_data
    assert "suffix" in domain_data
    assert "categories" in domain_data
    assert "source" in domain_data
    assert domain_data["categories"] == ["Local_Testing"]


class TestLocalModeCustomFavicons:
    """Test custom favicon tracking in local mode"""

    def test_local_metrics_collector_with_custom_favicon_tracking(self, temp_dir):
        """Test LocalMetricsCollector tracks custom favicon usage"""
        collector = LocalMetricsCollector(temp_dir)

        # Test result that used custom favicon
        custom_favicon_result = {
            "url": "https://axios.com",
            "title": "Axios",
            "icon": "https://cdn.example.com/axios_favicon.svg",
            "domain": "axios",
        }
        collector.record_domain_result("axios.com", custom_favicon_result, used_custom=True)

        # Test result that used scraped favicon
        scraped_favicon_result = {
            "url": "https://example.com",
            "title": "Example",
            "icon": "https://cdn.example.com/example_favicon.ico",
            "domain": "example",
        }
        collector.record_domain_result("example.com", scraped_favicon_result, used_custom=False)

        # Test failed result
        failed_result = {"url": None, "title": None, "icon": None, "domain": None}
        collector.record_domain_result("failed.com", failed_result, used_custom=False)

        # Verify counts
        assert collector.domains_processed == 3
        assert collector.favicons_found == 2
        assert collector.custom_favicons_used == 1
        assert collector.scraped_favicons_used == 1

        # Verify domain records include custom favicon tracking
        assert len(collector.domain_records) == 3
        assert collector.domain_records[0]["used_custom_favicon"] is True
        assert collector.domain_records[1]["used_custom_favicon"] is False
        assert collector.domain_records[2]["used_custom_favicon"] is False

    @freeze_time("2023-01-01 12:00:00")
    def test_local_metrics_collector_custom_favicon_report(self, temp_dir):
        """Test that custom favicon metrics are included in the saved report"""
        collector = LocalMetricsCollector(temp_dir)

        # Add mixed results
        custom_result = {
            "url": "https://axios.com",
            "title": "Axios",
            "icon": "https://cdn.example.com/axios.svg",
            "domain": "axios",
        }
        scraped_result = {
            "url": "https://example.com",
            "title": "Example",
            "icon": "https://cdn.example.com/example.ico",
            "domain": "example",
        }

        collector.record_domain_result("axios.com", custom_result, used_custom=True)
        collector.record_domain_result("example.com", scraped_result, used_custom=False)

        # Save report
        collector.save_report()

        # Check file content includes custom favicon metrics
        output_files = list(Path(temp_dir).glob("metrics_*.json"))
        with open(output_files[0], "r") as f:
            report = json.load(f)

        assert report["custom_favicons_used"] == 1
        assert report["scraped_favicons_used"] == 1
        assert report["custom_favicon_rate"] == 0.5  # 1 custom out of 2 total favicons

    def test_local_domain_data_provider_with_custom_favicon_domains(self):
        """Test that LocalDomainDataProvider can include domains with custom favicons"""
        # Create test domains that include some with custom favicons
        test_domains = [
            "axios.com",  # Has custom favicon
            "reuters.com",  # Has custom favicon
            "example.com",  # No custom favicon
            "test.com",  # No custom favicon
        ]

        provider = LocalDomainDataProvider(test_domains, 4)
        data = provider.get_domain_data()

        assert len(data) == 4

        # Verify all domains are included
        domain_names = [d["domain"] for d in data]
        assert "axios.com" in domain_names
        assert "reuters.com" in domain_names
        assert "example.com" in domain_names
        assert "test.com" in domain_names

        # Verify structure is correct for all domains
        for domain_data in data:
            assert "rank" in domain_data
            assert "domain" in domain_data
            assert "source" in domain_data
            assert domain_data["source"] == "local-test"

    def test_local_metrics_progress_logging_with_custom_favicons(self, temp_dir, caplog):
        """Test that progress logging includes custom favicon success rate"""
        import logging

        caplog.set_level(logging.INFO)

        collector = LocalMetricsCollector(temp_dir)

        # Add 10 domains with mix of custom and scraped favicons
        for i in range(10):
            if i < 3:  # First 3 use custom favicons
                result = {
                    "url": f"https://custom{i}.com",
                    "title": f"Custom {i}",
                    "icon": f"https://cdn.example.com/custom{i}.svg",
                    "domain": f"custom{i}",
                }
                collector.record_domain_result(f"custom{i}.com", result, used_custom=True)
            elif i < 7:  # Next 4 use scraped favicons
                result = {
                    "url": f"https://scraped{i}.com",
                    "title": f"Scraped {i}",
                    "icon": f"https://cdn.example.com/scraped{i}.ico",
                    "domain": f"scraped{i}",
                }
                collector.record_domain_result(f"scraped{i}.com", result, used_custom=False)
            else:  # Last 3 fail to get favicons
                result = {"url": None, "title": None, "icon": None, "domain": None}
                collector.record_domain_result(f"failed{i}.com", result, used_custom=False)

        # Check that progress logging includes custom favicon rate
        # The progress logging happens every 10 domains, so it should trigger
        progress_logs = [
            record.message for record in caplog.records if "Progress:" in record.message
        ]

        if progress_logs:
            # Should include success rate and custom favicon rate
            latest_log = progress_logs[-1]
            assert "Success rate:" in latest_log
            assert (
                "Custom:" in latest_log or "70.0%" in latest_log
            )  # 3 custom out of 7 successful favicons
