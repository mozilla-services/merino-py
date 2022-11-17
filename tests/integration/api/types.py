# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Module for type declarations for the integration test directory."""

from logging import LogRecord
from typing import Any, Callable

RequestSummaryLogDataFixture = Callable[[LogRecord], dict[str, Any]]
