# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from typing import Callable

from merino.providers import BaseProvider

Providers = dict[str, BaseProvider]
SetupProvidersFixture = Callable[[Providers], None]
TeardownProvidersFixture = Callable[[], None]
