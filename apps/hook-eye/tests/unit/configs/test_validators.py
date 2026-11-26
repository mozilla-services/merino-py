"""Unit tests for merino_hook_eye.configs validators."""

from typing import Any

import pytest
from dynaconf import Dynaconf, ValidationError

from merino_hook_eye.configs import _build_validators

# A valid value for every section the validators require, so each test only has to spell out
# the section it is exercising.
_DEFAULTS: dict[str, dict[str, Any]] = {
    "CCR_FOLLOWER": {
        "enabled": True,
        "url": "http://localhost:9201",
        "api_key": "",
        "request_timeout_sec": 5,
        "interval_sec": 60,
        "index_patterns": ["*wiki-*"],
    },
    "LOGGING": {"format": "mozlog", "level": "INFO", "can_propagate": False},
    "SENTRY": {"mode": "disabled", "dsn": "", "env": "dev", "traces_sample_rate": 0.0},
}


def _build(**overrides: dict[str, Any]) -> Dynaconf:
    """Build a Dynaconf instance carrying the service's validators, with whole-section
    overrides.
    """
    return Dynaconf(validators=_build_validators(), **{**_DEFAULTS, **overrides})


def test_defaults_are_valid() -> None:
    """The baseline used by the other tests passes validation."""
    _build().validators.validate()


@pytest.mark.parametrize(
    "overrides",
    [
        {"CCR_FOLLOWER": {**_DEFAULTS["CCR_FOLLOWER"], "enabled": "yes"}},
        {"CCR_FOLLOWER": {**_DEFAULTS["CCR_FOLLOWER"], "url": ""}},
        {"CCR_FOLLOWER": {**_DEFAULTS["CCR_FOLLOWER"], "request_timeout_sec": 0}},
        {"CCR_FOLLOWER": {**_DEFAULTS["CCR_FOLLOWER"], "interval_sec": 0}},
        {"CCR_FOLLOWER": {**_DEFAULTS["CCR_FOLLOWER"], "index_patterns": []}},
    ],
    ids=[
        "non-bool-check-toggle",
        "empty-url",
        "zero-timeout",
        "zero-interval",
        "no-index-patterns",
    ],
)
def test_invalid_settings_are_rejected(overrides: dict[str, dict[str, Any]]) -> None:
    """Settings that would break scraping fail validation at startup."""
    with pytest.raises(ValidationError):
        _build(**overrides).validators.validate()


@pytest.mark.parametrize(
    ("url", "api_key"),
    [
        ("http://localhost:9201", ""),
        ("https://follower.example:9243", ""),
        ("https://follower.example:9243", "c2VjcmV0"),
        ("HTTPS://follower.example:9243", "c2VjcmV0"),
    ],
    ids=["http-without-key", "https-without-key", "https-with-key", "uppercase-scheme"],
)
def test_follower_url_and_key_combinations_are_accepted(url: str, api_key: str) -> None:
    """An API key needs an https:// URL; without a key, plaintext http:// is allowed."""
    follower = {**_DEFAULTS["CCR_FOLLOWER"], "url": url, "api_key": api_key}

    _build(CCR_FOLLOWER=follower).validators.validate()


def test_plaintext_url_with_api_key_is_rejected() -> None:
    """An API key over http:// fails validation, without echoing the key."""
    follower = {**_DEFAULTS["CCR_FOLLOWER"], "url": "http://follower:9200", "api_key": "c2VjcmV0"}

    with pytest.raises(ValidationError, match="must use https://") as excinfo:
        _build(CCR_FOLLOWER=follower).validators.validate()

    assert "c2VjcmV0" not in str(excinfo.value)


@pytest.mark.parametrize(
    "follower",
    [
        {"enabled": False},
        {**_DEFAULTS["CCR_FOLLOWER"], "enabled": False, "url": "", "interval_sec": 0},
        {**_DEFAULTS["CCR_FOLLOWER"], "enabled": False, "api_key": "c2VjcmV0"},
    ],
    ids=["only-enabled", "invalid-values", "key-over-http"],
)
def test_disabled_follower_settings_are_not_checked(follower: dict[str, Any]) -> None:
    """A disabled check's other settings may be missing or invalid, since nothing uses them."""
    _build(CCR_FOLLOWER=follower).validators.validate()


def test_enabled_follower_settings_are_required() -> None:
    """An enabled check needs its settings."""
    with pytest.raises(ValidationError, match="ccr_follower.url"):
        _build(CCR_FOLLOWER={"enabled": True}).validators.validate()
