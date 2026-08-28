"""Unit tests for merino_fleece.configs validators."""

from typing import Any

import pytest
from dynaconf import Dynaconf, ValidationError

from merino_fleece.configs import _build_validators

# A valid value for every section the validators require, so each test only has to spell
# out the section it is actually exercising.
_DEFAULTS: dict[str, dict[str, Any]] = {
    "PII": {
        "model": "en_core_web_sm",
        "excluded_components": ["tok2vec"],
        "query_character_max": 100,
        "executor_max_workers": 4,
    },
    "LOGGING": {"format": "mozlog", "level": "INFO", "can_propagate": False},
    "SENTRY": {"mode": "disabled", "dsn": "", "env": "dev", "traces_sample_rate": 0.0},
    "PUBSUB": {"ack_deadline_sec": 30.0},
    "MARS": {
        "enabled": True,
        "base_url": "http://test-mars-api",
        "suggestion_url_path": "data",
        "countries": ["US"],
        "form_factors": ["desktop"],
        "connect_timeout_sec": 5.0,
        "request_timeout_sec": 10.0,
        "resync_interval_sec": 3600,
        "cron_interval_sec": 60,
    },
}


def _build(**overrides: dict[str, Any]) -> Dynaconf:
    """Build a fresh Dynaconf instance carrying the same validators as merino-fleece settings.

    Each override replaces a whole section, so a test states only the section it means to
    make invalid.
    """
    instance = Dynaconf(
        envvar_prefix="FLEECE_TEST",
        validators=_build_validators(),
        environments=False,
        **{**_DEFAULTS, **overrides},
    )
    return instance


def test_defaults_are_valid() -> None:
    """The baseline every other test overrides from passes validation."""
    _build().validators.validate()


def test_non_positive_ack_deadline_rejected() -> None:
    """A non-positive ack deadline fails validation."""
    instance = _build(PUBSUB={"ack_deadline_sec": 0.0})
    with pytest.raises(ValidationError):
        instance.validators.validate()


def test_invalid_model_rejected() -> None:
    """An unknown model name fails validation."""
    instance = _build(PII={**_DEFAULTS["PII"], "model": "bogus_model"})
    with pytest.raises(ValidationError):
        instance.validators.validate()


@pytest.mark.parametrize("model", ["en_core_web_sm", "en_core_web_md", "en_core_web_lg"])
def test_valid_models_accepted(model: str) -> None:
    """Each of the three allowed model names passes validation."""
    instance = _build(PII={**_DEFAULTS["PII"], "model": model})
    instance.validators.validate()


def test_query_character_max_upper_bound() -> None:
    """query_character_max above 500 fails validation."""
    instance = _build(PII={**_DEFAULTS["PII"], "query_character_max": 501})
    with pytest.raises(ValidationError):
        instance.validators.validate()


@pytest.mark.parametrize(
    "override",
    [
        pytest.param({"base_url": 42}, id="base_url_not_a_string"),
        pytest.param({"countries": "US"}, id="countries_not_a_list"),
        pytest.param({"connect_timeout_sec": 0.0}, id="non_positive_timeout"),
        pytest.param({"resync_interval_sec": 0}, id="non_positive_resync_interval"),
        pytest.param({"cron_interval_sec": -1}, id="negative_cron_interval"),
    ],
)
def test_invalid_mars_settings_rejected(override: dict[str, Any]) -> None:
    """Malformed MARS settings fail validation at startup rather than at fetch time."""
    instance = _build(MARS={**_DEFAULTS["MARS"], **override})
    with pytest.raises(ValidationError):
        instance.validators.validate()


def test_missing_mars_section_rejected() -> None:
    """The MARS settings are required, so a missing section fails validation."""
    instance = Dynaconf(
        envvar_prefix="FLEECE_TEST",
        validators=_build_validators(),
        environments=False,
        **{key: value for key, value in _DEFAULTS.items() if key != "MARS"},
    )
    with pytest.raises(ValidationError):
        instance.validators.validate()
