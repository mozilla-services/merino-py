# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Shared fixtures for the Polygon backend unit tests."""

from typing import Any, Callable

import pytest


@pytest.fixture(name="search_result")
def fixture_search_result() -> Callable[..., dict[str, Any]]:
    """Return a factory for reference tickers search result entries."""

    def make(
        ticker: str, name: str, security_type: str = "CS", **overrides: Any
    ) -> dict[str, Any]:
        return {
            "ticker": ticker,
            "name": name,
            "market": "stocks",
            "locale": "us",
            "primary_exchange": "XNAS",
            "type": security_type,
            "active": True,
            **overrides,
        }

    return make
