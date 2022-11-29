# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the config_logging.py module."""

import pytest

from merino.config import settings
from merino.config_logging import configure_logging


def test_configure_logging_invalid_format():
    """Test that configure_logging will raise a ValueError when encountering unknown log
    formats.
    """
    old_format = settings.logging.format
    settings.logging.format = "invalid"

    with pytest.raises(ValueError) as excinfo:
        configure_logging()

    assert "Invalid log format:" in str(excinfo)

    settings.logging.format = old_format


def test_configure_logging_mozlog_production():
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
