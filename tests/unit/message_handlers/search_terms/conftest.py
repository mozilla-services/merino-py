# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Shared fixtures for the search term submission message handler tests."""

from collections.abc import Callable
from datetime import UTC, datetime

import pytest

from merino_common.models.suggest_logging import SuggestRequestParams

# A fixed submission timestamp, so tests can assert on the serialized form.
SUBMITTED_AT = datetime(2022, 12, 18, hour=15, minute=58, second=41, tzinfo=UTC)
SUBMITTED_AT_ISO = "2022-12-18T15:58:41+00:00"


@pytest.fixture(name="params")
def fixture_params() -> Callable[[str], SuggestRequestParams]:
    """Return a factory that builds a minimal SuggestRequestParams for a given query."""

    def _build(query: str) -> SuggestRequestParams:
        return SuggestRequestParams(
            query=query,
            code=200,
            rid="rid",
            client_variants="",
            requested_providers="",
            browser="Firefox",
            os_family="macos",
            form_factor="desktop",
            submitted_at=SUBMITTED_AT,
        )

    return _build
