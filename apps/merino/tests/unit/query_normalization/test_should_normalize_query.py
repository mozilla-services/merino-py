# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the query-normalization routing helper (_should_normalize_query)."""

from unittest.mock import patch

import pytest

from merino.providers.suggest.manager import ProviderType
from merino.web.api_v1 import _should_normalize_query

_NORM_PROVIDERS = frozenset({ProviderType.SPORTS, ProviderType.POLYGON, ProviderType.ADM})


@patch("merino.web.api_v1.NORMALIZATION_PROVIDERS", _NORM_PROVIDERS)
def test_should_normalize_query_newtab_is_never_normalized() -> None:
    """New Tab requests always receive the raw query."""
    assert _should_normalize_query(ProviderType.ADM, "newtab") is False


@patch("merino.web.api_v1.NORMALIZATION_PROVIDERS", frozenset({ProviderType.SPORTS}))
def test_should_normalize_query_provider_not_in_list() -> None:
    """A provider absent from the normalization list receives the raw query."""
    assert _should_normalize_query(ProviderType.WIKIPEDIA, "urlbar") is False


@patch("merino.web.api_v1.NORMALIZATION_PROVIDERS", _NORM_PROVIDERS)
def test_should_normalize_query_graduated_provider_always_on() -> None:
    """Graduated providers (e.g. sports) are always normalized off New Tab."""
    assert _should_normalize_query(ProviderType.SPORTS, "urlbar") is True


@pytest.mark.parametrize("fuzzy_enabled", [True, False])
@patch("merino.web.api_v1.NORMALIZATION_PROVIDERS", _NORM_PROVIDERS)
def test_should_normalize_query_adm_follows_config_flag(fuzzy_enabled: bool) -> None:
    """AMP normalization is gated on the combined config flag."""
    with patch("merino.web.api_v1.AMP_FUZZY_ENABLED", fuzzy_enabled):
        assert _should_normalize_query(ProviderType.ADM, "urlbar") is fuzzy_enabled
