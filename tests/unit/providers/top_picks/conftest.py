# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Module for test configurations for the Top Picks provider unit test directory."""

from typing import Any

import pytest

from merino.configs.config import settings
from merino.providers.top_picks.backends.top_picks import TopPicksBackend
from merino.providers.top_picks.provider import Provider


@pytest.fixture(name="domain_blocklist")
def fixture_top_picks_domain_blocklist() -> set[str]:
    """Create domain_blocklist."""
    return {"baddomain"}


@pytest.fixture(name="top_picks_backend_parameters")
def fixture_top_picks_backend_parameters(domain_blocklist: set[str]) -> dict[str, Any]:
    """Define Top Picks backed parameters for test."""
    return {
        "top_picks_file_path": settings.providers.top_picks.top_picks_file_path,
        "query_char_limit": settings.providers.top_picks.query_char_limit,
        "firefox_char_limit": settings.providers.top_picks.firefox_char_limit,
        "domain_blocklist": domain_blocklist,
    }


@pytest.fixture(name="backend")
def fixture_backend(
    top_picks_backend_parameters: dict[str, Any],
) -> TopPicksBackend:
    """Create a Top Pick backend object for test."""
    backend = TopPicksBackend(**top_picks_backend_parameters)
    return backend


@pytest.fixture(name="top_picks_parameters")
def fixture_top_picks_parameters() -> dict[str, Any]:
    """Define Top Pick provider parameters for test."""
    return {
        "name": "top_picks",
        "enabled_by_default": settings.providers.top_picks.enabled_by_default,
        "score": settings.providers.top_picks.score,
    }


@pytest.fixture(name="top_picks")
def fixture_top_picks(backend: TopPicksBackend, top_picks_parameters: dict[str, Any]) -> Provider:
    """Create Top Pick Provider for test."""
    return Provider(backend=backend, **top_picks_parameters)  # type: ignore [arg-type]
