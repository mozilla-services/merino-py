import pytest
from pydantic import ValidationError

from merino.featureflags import FeatureFlags, session_id_context


def test_missing():
    flags = FeatureFlags()
    assert not flags.is_enabled("test-missing")


def test_enabled():
    flags = FeatureFlags()
    assert flags.is_enabled("test-enabled")


def test_not_enabled():
    flags = FeatureFlags()
    assert not flags.is_enabled("test-not-enabled")


def test_no_scheme_no_session_id(caplog):
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
    with pytest.raises(ValidationError):
        FeatureFlags(flags=config)
