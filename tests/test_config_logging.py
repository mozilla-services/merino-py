import pytest

from merino.config import settings
from merino.config_logging import configure_logging


def test_invalid_format():
    old_format = settings.logging.format
    settings.logging.format = "invalid"

    with pytest.raises(ValueError) as excinfo:
        configure_logging()

    assert "Invalid log format:" in str(excinfo)

    settings.logging.format = old_format


def test_mozlog_production():
    settings.configure(FORCE_ENV_FOR_DYNACONF="production")
    old_format = settings.logging.format
    settings.logging.format = "pretty"

    with pytest.raises(ValueError) as excinfo:
        configure_logging()

    assert "Log format must be 'mozlog' in production" in str(excinfo)

    settings.logging.format = old_format
