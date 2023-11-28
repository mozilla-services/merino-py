# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for domain_metadata_diff.py module."""

import json

import pytest

from merino.jobs.navigational_suggestions.domain_metadata_diff import DomainDiff


@pytest.fixture(name="json_domain_data_old")
def fixture_json_domain_data() -> str:
    """Return a JSON string of top picks data for mocking."""
    return json.dumps(
        {
            "domains": [
                {
                    "rank": 1,
                    "title": "Example",
                    "domain": "example",
                    "url": "https://example.com",
                    "icon": "",
                    "categories": ["web-browser"],
                    "similars": ["exxample", "exampple", "eexample"],
                },
                {
                    "rank": 2,
                    "title": "Firefox",
                    "domain": "firefox",
                    "url": "https://firefox.com",
                    "icon": "",
                    "categories": ["web-browser"],
                    "similars": [
                        "firefoxx",
                        "foyerfox",
                        "fiirefox",
                        "firesfox",
                        "firefoxes",
                    ],
                },
                {
                    "rank": 3,
                    "title": "Mozilla",
                    "domain": "mozilla",
                    "url": "https://mozilla.org/en-US/",
                    "icon": "",
                    "categories": ["web-browser"],
                    "similars": ["mozzilla", "mozila"],
                },
                {
                    "rank": 4,
                    "title": "Abc",
                    "domain": "abc",
                    "url": "https://abc.test",
                    "icon": "",
                    "categories": ["web-browser"],
                    "similars": ["aa", "ab", "acb", "acbc", "aecbc"],
                },
                {
                    "rank": 5,
                    "title": "BadDomain",
                    "domain": "baddomain",
                    "url": "https://baddomain.test",
                    "icon": "",
                    "categories": ["web-browser"],
                    "similars": ["bad", "badd"],
                },
                {
                    "rank": 6,
                    "title": "Subdomain Test",
                    "domain": "subdomain",
                    "url": "https://sub.subdomain.test",
                    "icon": "",
                    "categories": ["web-browser"],
                    "similars": [
                        "sub",
                    ],
                },
            ]
        }
    )


@pytest.fixture(name="json_domain_data_latest")
def fixture_json_domain_data_latest() -> str:
    """Return a JSON string of top picks data for mocking."""
    return json.dumps(
        {
            "domains": [
                {
                    "rank": 1,
                    "title": "TestExample",
                    "domain": "test-example",
                    "url": "https://testexample.com",
                    "icon": "",
                    "categories": ["web-browser"],
                    "similars": ["exxample", "exampple", "eexample"],
                },
                {
                    "rank": 2,
                    "title": "Firefox",
                    "domain": "firefox",
                    "url": "https://test.firefox.com",
                    "icon": "",
                    "categories": ["web-browser"],
                    "similars": [
                        "firefoxx",
                        "foyerfox",
                        "fiirefox",
                        "firesfox",
                        "firefoxes",
                    ],
                },
                {
                    "rank": 3,
                    "title": "Mozilla",
                    "domain": "mozilla",
                    "url": "https://mozilla.org/en-US/",
                    "icon": "",
                    "categories": ["web-browser"],
                    "similars": ["mozzilla", "mozila"],
                },
                {
                    "rank": 4,
                    "title": "Abc",
                    "domain": "abc",
                    "url": "https://abc.test",
                    "icon": "",
                    "categories": ["web-browser"],
                    "similars": ["aa", "ab", "acb", "acbc", "aecbc"],
                },
                {
                    "rank": 5,
                    "title": "BadDomain",
                    "domain": "baddomain",
                    "url": "https://baddomain.test",
                    "icon": "",
                    "categories": ["web-browser"],
                    "similars": ["bad", "badd"],
                },
                {
                    "rank": 6,
                    "title": "Subdomain Test",
                    "domain": "subdomain",
                    "url": "https://sub.subdomain.test",
                    "icon": "",
                    "categories": ["web-browser"],
                    "similars": [
                        "sub",
                    ],
                },
            ]
        }
    )


# def test_get_latest_file_for_diff(
#     mock_favicon_downloader,
#     caplog: LogCaptureFixture,
#     filter_caplog: FilterCaplogFixture,
#     remote_blob,
#     remote_client,
#     mocker,
# ) -> None:
#     """Test acquiring the latest file data from mock GCS bucket.
#     Also checks case if there is no data.
#     """
#     mocker.patch(
#         "merino.jobs.navigational_suggestions.domain_metadata_uploader.Client"
#     ).return_value = remote_client
#     caplog.set_level(INFO)
#     default_domain_metadata_uploader = DomainMetadataUploader(
#         destination_gcp_project="dummy_gcp_project",
#         destination_bucket_name="dummy_gcs_bucket",
#         destination_cdn_hostname="",
#         force_upload=False,
#         favicon_downloader=mock_favicon_downloader,
#     )

#     result = default_domain_metadata_uploader.get_latest_file_for_diff(
#         client=remote_client
#     )
#     records: list[LogRecord] = filter_caplog(
#         caplog.records, "merino.jobs.navigational_suggestions.domain_metadata_uploader"
#     )
#     assert isinstance(result, dict)
#     assert result["domains"]
#     assert len(result["domains"]) == 6

#     assert len(records) == 1
#     assert records[0].message.startswith(f"Domain file {remote_blob.name} acquired.")


def test_process_domains(json_domain_data_latest, json_domain_data_old) -> None:
    """Test that the domain list can be processed and a list of all
    second-level domains are returned.
    """
    domain_diff = DomainDiff(
        latest_domain_data=json_domain_data_latest, old_domain_data=json_domain_data_old
    )
    expected_domains = [
        "test-example",
        "firefox",
        "mozilla",
        "abc",
        "baddomain",
        "subdomain",
    ]
    processed_domains = domain_diff.process_domains(
        domain_data=json.loads(json_domain_data_latest)
    )

    assert processed_domains == expected_domains


def test_process_urls(json_domain_data_latest, json_domain_data_old) -> None:
    """Test that the domain list can be processed and a list of all
    urls are returned.
    """
    domain_diff = DomainDiff(
        latest_domain_data=json_domain_data_latest, old_domain_data=json_domain_data_old
    )
    expected_urls = [
        "https://testexample.com",
        "https://test.firefox.com",
        "https://mozilla.org/en-US/",
        "https://abc.test",
        "https://baddomain.test",
        "https://sub.subdomain.test",
    ]
    processed_urls = domain_diff.process_urls(
        domain_data=json.loads(json_domain_data_latest)
    )

    assert processed_urls == expected_urls


def test_process_categories(json_domain_data_latest, json_domain_data_old) -> None:
    """Test that the domain list can be processed and a list of all
    distinct categories.
    """
    domain_diff = DomainDiff(
        latest_domain_data=json_domain_data_latest, old_domain_data=json_domain_data_old
    )
    expected_categories = ["web-browser"]
    processed_categories = domain_diff.process_categories(
        domain_data=json.loads(json_domain_data_latest)
    )

    assert processed_categories == expected_categories


def test_check_url_for_subdomain(json_domain_data_latest, json_domain_data_old) -> None:
    """Test that the domain list can be processed and a list of all
    distinct categories.
    """
    domain_diff = DomainDiff(
        latest_domain_data=json_domain_data_latest, old_domain_data=json_domain_data_old
    )
    expected_subdomains = [
        {"rank": 1, "domain": "test-example", "url": "https://testexample.com"},
        {"rank": 2, "domain": "firefox", "url": "https://test.firefox.com"},
        {"rank": 6, "domain": "subdomain", "url": "https://sub.subdomain.test"},
    ]
    subdomain_occurences = domain_diff.check_url_for_subdomain(
        domain_data=json.loads(json_domain_data_latest)
    )

    assert subdomain_occurences == expected_subdomains


def test_compare_top_picks(json_domain_data_latest, json_domain_data_old) -> None:
    """Test comparision of latest and previous Top Picks data."""
    domain_diff = DomainDiff(
        latest_domain_data=json_domain_data_latest, old_domain_data=json_domain_data_old
    )
    result = domain_diff.compare_top_picks(
        new_top_picks=json_domain_data_latest, old_top_picks=json_domain_data_old
    )
    expected_categories = ["web-browser"]
    expected_unchanged = {"subdomain", "firefox", "baddomain", "abc", "mozilla"}
    expected_added_domains = {"test-example"}
    expected_added_urls = {"https://testexample.com", "https://test.firefox.com"}
    expected_subdomains = [
        {"rank": 1, "domain": "test-example", "url": "https://testexample.com"},
        {"rank": 2, "domain": "firefox", "url": "https://test.firefox.com"},
        {"rank": 6, "domain": "subdomain", "url": "https://sub.subdomain.test"},
    ]
    assert result[0] == expected_categories
    assert result[1] == expected_unchanged
    assert result[2] == expected_added_domains
    assert result[3] == expected_added_urls
    assert result[4] == expected_subdomains


def test_create_diff_file(json_domain_data_latest, json_domain_data_old) -> None:
    """Test that the expected diff file is generated."""
    domain_diff = DomainDiff(
        latest_domain_data=json_domain_data_latest, old_domain_data=json_domain_data_old
    )
    (
        categories,
        unchanged_domains,
        added_domains,
        added_urls,
        subdomains,
    ) = domain_diff.compare_top_picks(
        new_top_picks=json_domain_data_latest, old_top_picks=json_domain_data_old
    )

    diff_file = domain_diff.create_diff_file(
        file_name="test_blob.json",
        categories=categories,
        unchanged=unchanged_domains,
        domains=added_domains,
        urls=added_urls,
        subdomains=subdomains,
    )

    assert diff_file.startswith("Top Picks Diff File")
    assert "Newly added domains: 1" in diff_file
    assert "Domains containing subdomain: 3" in diff_file
