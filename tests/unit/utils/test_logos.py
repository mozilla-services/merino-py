# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the logos provider module."""

import logging

import pytest

from merino.utils.logos import get_logo_url, load_manifest, LogoCategory, LogoManifest
from tests.types import FilterCaplogFixture
from merino.configs import settings

host = f"https://{settings.image_gcs_v2.cdn_hostname}"
bucket = settings.image_gcs_v2.gcs_bucket


@pytest.mark.parametrize(
    "category,key",
    [
        (LogoCategory.Airline, "aa"),
        (LogoCategory.Airline, "AA"),
    ],
    ids=["lowercase", "capitalized"],
)
def test_get_logo_url_exists(category: LogoCategory, key: str) -> None:
    """Returns the URL from the manifest when the entry exists (regardless of capitalization)."""
    result = get_logo_url(category, key)

    assert str(result) == f"{host}/logos/airline/airline_aa.png"


def test_get_logo_url_not_found(
    caplog: pytest.LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
    statsd_mock,
    mocker,
) -> None:
    """Returns None when the manifest has no entry for the given category and key."""
    mocker.patch("merino.utils.logos.metrics_client", statsd_mock)
    mocker.patch("merino.utils.logos._REPORTED_MISSES", set())
    sentry_capture = mocker.patch("merino.utils.logos.sentry_sdk.capture_message")

    with caplog.at_level(logging.WARNING):
        result = get_logo_url(LogoCategory.MLB, "zzzzz")

    assert result is None
    records = filter_caplog(caplog.records, "merino.utils.logos")
    assert len(records) == 1
    assert "mlb" in records[0].message
    assert "zzzzz" in records[0].message

    # Increments miss metric with the normalized key so dashboards can show
    # which specific logo is missing, not just the category.
    statsd_mock.increment.assert_called_once_with(
        "manifest.lookup",
        tags={"name": "logos.mlb", "key": "ZZZZZ", "result": "miss"},
    )

    # Fires a Sentry event at error level so on-call gets a single triageable
    # Issue per unique missing logo rather than a line in GCP Logs nobody reads.
    sentry_capture.assert_called_once()
    call = sentry_capture.call_args
    assert call.args[0] == "Missing logo: category=mlb key=ZZZZZ"
    assert call.kwargs["level"] == "error"


def test_get_logo_url_not_found_reports_to_sentry_once_per_process(
    statsd_mock,
    mocker,
) -> None:
    """Repeated misses for the same (category, key) fire Sentry at most once.

    Prevents chatty misses (e.g. sustained bursts on a known-bad key) from
    burning event quota. The metric still fires on every miss since Grafana
    relies on the rate.
    """
    mocker.patch("merino.utils.logos.metrics_client", statsd_mock)
    mocker.patch("merino.utils.logos._REPORTED_MISSES", set())
    sentry_capture = mocker.patch("merino.utils.logos.sentry_sdk.capture_message")

    for _ in range(5):
        assert get_logo_url(LogoCategory.MLB, "zzzzz") is None

    sentry_capture.assert_called_once()
    assert statsd_mock.increment.call_count == 5


@pytest.mark.restore_load_manifest
def test_load_manifest_parses_real_file() -> None:
    """Reads and validates the shipped logos_manifest.json file.

    Guards against file corruption, schema drift, or accidental deletion.
    """
    load_manifest.cache_clear()

    manifest = load_manifest()

    assert isinstance(manifest, LogoManifest)
