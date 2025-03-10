# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Type definitions for unit test modules."""

from typing import Callable

from merino.providers.suggest.base import SuggestionRequest

SuggestionRequestFixture = Callable[[str], SuggestionRequest]
