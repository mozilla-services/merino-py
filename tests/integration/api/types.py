# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Type definitions for the integration test modules."""

from logging import LogRecord
from typing import Callable

from merino.utils.log_data_creators import RequestSummaryLogDataModel

RequestSummaryLogDataFixture = Callable[[LogRecord], RequestSummaryLogDataModel]
