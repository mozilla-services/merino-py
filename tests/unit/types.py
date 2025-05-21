# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Type definitions for unit test modules."""

from typing import Callable, Optional

from merino.middleware.geolocation import Location
from merino.middleware.user_agent import UserAgent
from merino.providers.suggest.base import SuggestionRequest

SuggestionRequestFixture = Callable[
    [str, Optional[Location], Optional[UserAgent]], SuggestionRequest
]
