# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Shared fixtures for the search term submission message handler tests."""

from collections.abc import Callable

import pytest

from merino_common.models.suggest_logging import SuggestRequestParams


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
        )

    return _build
