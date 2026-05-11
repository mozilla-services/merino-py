# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""WCS integration test fixtures."""

from collections.abc import Iterator

import pytest

from merino.main import app
from merino.providers.wcs import get_provider as get_wcs_provider
from tests.wcs.factories import build_provider


@pytest.fixture(autouse=True)
def wcs_provider_override() -> Iterator[None]:
    """Serve deterministic WCS data without connecting to Redis."""
    provider = build_provider()
    app.dependency_overrides[get_wcs_provider] = lambda: provider
    yield
    del app.dependency_overrides[get_wcs_provider]
