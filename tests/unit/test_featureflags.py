# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the featureflags.py module.

This module depends on testing.toml
"""

import pytest
from pydantic import ValidationError

from merino.featureflags import FeatureFlags, session_id_context


def test__missing():
    """Test that is_enabled will return False if a flag is undefined."""
    flags = FeatureFlags()
    assert not flags.is_enabled("test-missing")


def test_enabled():
    """Test that is_enabled will return True if a flag is defined as enabled."""
    flags = FeatureFlags()
    assert flags.is_enabled("test-enabled")


def test_not_enabled():
    """Test that is_enabled will return False if a flag is defined as disabled."""
    flags = FeatureFlags()
    assert not flags.is_enabled("test-not-enabled")


def test_no_scheme_no_session_id(caplog):
    """Test that if a flag is defined without a 'scheme' then is_enabled will return
    False and an error message will be logged.
    """
    import logging

    caplog.set_level(logging.ERROR)
    flags = FeatureFlags()
    assert not flags.is_enabled("test-no-scheme")

    assert len(caplog.records) == 1
    assert caplog.messages[0] == "Expected a session_id but none exist in this context"


@pytest.mark.parametrize(
    ["bucket_id", "want"],
    [
        ("000", True),
        ("fff", False),
    ],
    ids=["session_id_on", "session_id_off"],
)
def test_no_scheme_default_session_id(bucket_id: str, want: bool):
    """Test that is_enabled returns as expected given a flag with no 'scheme'
    definition and a given session_id_context.
    """
    session_id_context.set(bucket_id)
    flags = FeatureFlags()
    assert flags.is_enabled("test-no-scheme") is want


@pytest.mark.parametrize(
    ["bucket_id", "want"],
    [
        (b"\x00\x00\x00\x00", True),
        (b"\xff\xff\xff\xff", False),
    ],
    ids=["enabed_on", "enabled_off"],
)
def test_enabled_perc(bucket_id: str, want: bool):
    """Test for feature flags with "random" scheme and passing in bucket_for value."""
    flags = FeatureFlags()
    assert flags.is_enabled("test-perc-enabled", bucket_for=bucket_id) is want


@pytest.mark.parametrize(
    ["bucket_id", "want"],
    [
        ("000", True),
        ("fff", False),
    ],
    ids=["session_id_on", "session_id_off"],
)
def test_enabled_perc_session(bucket_id: str, want: bool):
    """Test for feature flags with "random" scheme and passing in bucket_for value."""
    session_id_context.set(bucket_id)
    flags = FeatureFlags()
    assert flags.is_enabled("test-perc-enabled-session") is want


@pytest.mark.parametrize(
    "config",
    [
        {"invalid-scheme": {"scheme": "invalid", "enabled": 0}},
        {"enabled-range": {"enabled": 42}},
    ],
    ids=["invalid-scheme", "enabled-range"],
)
def test_raises_malformed_config(config: dict):
    """Test that a ValidationError is raised given a malformed flag configuration."""
    with pytest.raises(ValidationError):
        FeatureFlags(flags=config)
