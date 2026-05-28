# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the config_logging.py module."""

import logging
from typing import Any

import pytest

from merino_common.app_configs.config_logging import configure_logging


@pytest.fixture(autouse=True)
def restore_logger_disabled_state() -> Any:
    """Restore each logger's ``disabled`` flag after the test.

    ``configure_logging`` calls ``logging.config.dictConfig``, which defaults to
    ``disable_existing_loggers=True``. Without this fixture, configuring one logger here
    silently disables loggers created elsewhere (e.g. ``merino_common.routers.dockerflow``
    imported during collection) and breaks unrelated tests that rely on caplog.
    """
    logger_dict = logging.root.manager.loggerDict
    snapshot = {
        name: logger.disabled
        for name, logger in logger_dict.items()
        if isinstance(logger, logging.Logger)
    }
    yield
    for name, disabled in snapshot.items():
        logger = logger_dict.get(name)
        if isinstance(logger, logging.Logger):
            logger.disabled = disabled


def test_configure_logging_invalid_format() -> None:
    """configure_logging raises ValueError when given an unknown log format."""
    with pytest.raises(ValueError, match="Invalid log format"):
        configure_logging(
            log_format="invalid",
            level="INFO",
            can_propagate=False,
            current_env="development",
            logger_name="merino",
        )


def test_configure_logging_mozlog_production() -> None:
    """configure_logging raises ValueError if production runs with a non-mozlog format."""
    with pytest.raises(ValueError, match="Log format must be 'mozlog' in production"):
        configure_logging(
            log_format="pretty",
            level="INFO",
            can_propagate=False,
            current_env="production",
            logger_name="merino",
        )


@pytest.mark.parametrize(
    ("log_format", "expected_handler"),
    [("mozlog", "console-mozlog"), ("pretty", "console-pretty")],
    ids=["mozlog", "pretty"],
)
def test_configure_log_handler_assigned(log_format: str, expected_handler: str) -> None:
    """The configured logger uses the handler matching the requested log_format."""
    configure_logging(
        log_format=log_format,
        level="INFO",
        can_propagate=False,
        current_env="development",
        logger_name="merino",
    )

    log_manager: Any = logging.root.manager
    handler_name: Any = log_manager.loggerDict["merino"].handlers[0].name
    assert handler_name == expected_handler


def test_configure_logging_uses_provided_logger_name() -> None:
    """The logger named by `logger_name` is configured (not a hardcoded "merino")."""
    configure_logging(
        log_format="mozlog",
        level="INFO",
        can_propagate=False,
        current_env="development",
        logger_name="merino_fleece",
    )

    log_manager: Any = logging.root.manager
    assert "merino_fleece" in log_manager.loggerDict
    assert log_manager.loggerDict["merino_fleece"].handlers[0].name == "console-mozlog"
