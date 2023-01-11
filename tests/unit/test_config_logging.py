# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the config_logging.py module."""


import logging
from typing import Any

import pytest

from merino.config import settings
from merino.config_logging import configure_logging


def test_configure_logging_invalid_format() -> None:
    """Test that configure_logging will raise a ValueError when encountering unknown log
    formats.
    """
    old_format = settings.logging.format
    settings.logging.format = "invalid"

    with pytest.raises(ValueError) as excinfo:
        configure_logging()

    assert "Invalid log format:" in str(excinfo)

    settings.logging.format = old_format


def test_configure_logging_mozlog_production() -> None:
    """Test that configure_logging will raise a ValueError when using a format other
    than 'mozlog' in production.
    """
    with settings.using_env("production"):
        old_format = settings.logging.format
        settings.logging.format = "pretty"

        with pytest.raises(ValueError) as excinfo:
            configure_logging()

        assert "Log format must be 'mozlog' in production" in str(excinfo)

        settings.logging.format = old_format


def test_configure_log_handler_assigned_mozlog() -> None:
    """Test that the log handler is assigned as expected when the configured format is 'mozlog'"""
    settings.logging.format = "mozlog"
    configure_logging()

    merino_log_manager: Any = logging.root.manager
    merino_logger: Any = merino_log_manager.loggerDict["merino"].handlers[0].name
    assert merino_logger == "console-mozlog"


def test_configure_log_handler_assigned_pretty() -> None:
    """Test that the log handler is assigned as expected when the configured format is 'pretty'"""
    settings.logging.format = "pretty"
    configure_logging()

    merino_log_manager: Any = logging.root.manager
    merino_logger: Any = merino_log_manager.loggerDict["merino"].handlers[0].name
    assert merino_logger == "console-pretty"
