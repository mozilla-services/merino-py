# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the config_sentry.py module."""

import pytest

from merino.config_sentry import configure_sentry


@pytest.fixture(name="sentry_init")
def sentry_init() -> None:
    """Initialize sentry instance fixture."""
    configure_sentry()
