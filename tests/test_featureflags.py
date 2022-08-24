import pytest

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


def test_invalid_scheme(caplog):
    import logging

    caplog.set_level(logging.WARNING)

    flags = FeatureFlags()
    enabled = flags.is_enabled("test-invalid-scheme")
    assert not enabled

    assert len(caplog.records) == 1
    assert (
        caplog.messages[0]
        == "bucketing_id: scheme must be on of `random`, `session`. got `invalid`"
    )


def test_no_scheme():
    flags = FeatureFlags()
    assert not flags.is_enabled("test-no-scheme")


@pytest.mark.parametrize(
    "bucket_id, want",
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
    "bucket_id, want",
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
    "bucket_id, want",
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
