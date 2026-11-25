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
