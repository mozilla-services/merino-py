# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the config_logging.py module."""

import logging
from typing import Any

import pytest

from merino_common.app_configs.config_logging import configure_logging


def test_configure_logging_invalid_format() -> None:
    """configure_logging raises ValueError when given an unknown log format."""
    with pytest.raises(ValueError, match="Invalid log format"):
        configure_logging(
            log_format="invalid",
            level="INFO",
            can_propagate=False,
            current_env="development",
        )


def test_configure_logging_mozlog_production() -> None:
    """configure_logging raises ValueError if production runs with a non-mozlog format."""
    with pytest.raises(ValueError, match="Log format must be 'mozlog' in production"):
        configure_logging(
            log_format="pretty",
            level="INFO",
            can_propagate=False,
            current_env="production",
        )


def test_configure_log_handler_assigned_mozlog() -> None:
    """The merino logger uses the console-mozlog handler when log_format is 'mozlog'."""
    configure_logging(
        log_format="mozlog",
        level="INFO",
        can_propagate=False,
        current_env="development",
    )

    merino_log_manager: Any = logging.root.manager
    merino_logger: Any = merino_log_manager.loggerDict["merino"].handlers[0].name
    assert merino_logger == "console-mozlog"


def test_configure_log_handler_assigned_pretty() -> None:
    """The merino logger uses the console-pretty handler when log_format is 'pretty'."""
    configure_logging(
        log_format="pretty",
        level="INFO",
        can_propagate=False,
        current_env="development",
    )

    merino_log_manager: Any = logging.root.manager
    merino_logger: Any = merino_log_manager.loggerDict["merino"].handlers[0].name
    assert merino_logger == "console-pretty"
