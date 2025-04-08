"""Integration tests for local_mode module"""

import json
import shutil
import tempfile
from pathlib import Path

import pytest
from freezegun import freeze_time

from merino.jobs.navigational_suggestions.local_mode import (
    LocalMetricsCollector,
    LocalDomainDataProvider,
)
from merino.jobs.navigational_suggestions.custom_domains import CUSTOM_DOMAINS


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
