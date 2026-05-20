"""Unit tests for merino_fleece.configs validators."""

import pytest
from dynaconf import Dynaconf, ValidationError

from merino_fleece.configs import _build_validators


def _build(**overrides) -> Dynaconf:
    """Build a fresh Dynaconf instance carrying the same validators as merino-fleece settings."""
    instance = Dynaconf(
        envvar_prefix="FLEECE_TEST",
        validators=_build_validators(),
        environments=False,
        **overrides,
    )
    return instance


def test_invalid_model_rejected() -> None:
    """An unknown model name fails validation."""
    instance = _build(
        PII={
            "model": "bogus_model",
            "excluded_components": ["tok2vec"],
            "query_character_max": 100,
        },
        LOGGING={"format": "mozlog", "level": "INFO", "can_propagate": False},
        SENTRY={"mode": "disabled", "dsn": "", "env": "dev", "traces_sample_rate": 0.0},
    )
    with pytest.raises(ValidationError):
        instance.validators.validate()


@pytest.mark.parametrize("model", ["en_core_web_sm", "en_core_web_md", "en_core_web_lg"])
def test_valid_models_accepted(model: str) -> None:
    """Each of the three allowed model names passes validation."""
    instance = _build(
        PII={
            "model": model,
            "excluded_components": ["tok2vec"],
            "query_character_max": 100,
        },
        LOGGING={"format": "mozlog", "level": "INFO", "can_propagate": False},
        SENTRY={"mode": "disabled", "dsn": "", "env": "dev", "traces_sample_rate": 0.0},
    )
    instance.validators.validate()


def test_query_character_max_upper_bound() -> None:
    """query_character_max above 500 fails validation."""
    instance = _build(
        PII={
            "model": "en_core_web_sm",
            "excluded_components": ["tok2vec"],
            "query_character_max": 501,
        },
        LOGGING={"format": "mozlog", "level": "INFO", "can_propagate": False},
        SENTRY={"mode": "disabled", "dsn": "", "env": "dev", "traces_sample_rate": 0.0},
    )
    with pytest.raises(ValidationError):
        instance.validators.validate()
