# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the api_v1.py utility module."""

import logging

from fastapi import HTTPException
import pytest
from unittest.mock import Mock
from fastapi import Request

from merino.middleware import ScopeKey
from merino.middleware.geolocation import Location
from merino.utils.api.query_params import (
    get_accepted_languages,
    refine_geolocation_for_suggestion,
    validate_suggest_custom_location_params,
)
from tests.types import FilterCaplogFixture


@pytest.fixture(name="geolocation")
def fixture_geolocation() -> Location:
    """Return a test Location."""
    return Location(
        country="US",
        country_name="United States",
        regions=["WA"],
        region_names=["Washington"],
        city="Milton",
        dma=819,
        postal_code="98354",
    )


@pytest.mark.parametrize(
    ("languages", "expected_filtered_languages"),
    [
        ("*", ["en-US"]),
        ("en-US", ["en-US"]),
        ("en-US,en;q=0.5", ["en-US", "en"]),
        ("en-US,en;q=0.9,zh-CN;q=0.7", ["en-US", "en", "zh-CN"]),
        ("en-CA;q=invalid", ["en-US"]),
    ],
)
def test_get_accepted_languages(languages, expected_filtered_languages):
    """Test Accept-Language Header parsing and filtering."""
    assert get_accepted_languages(languages) == expected_filtered_languages


@pytest.mark.parametrize(
    ("city", "region", "country"),
    [
        (None, "MA", "US"),
        ("Boston", None, None),
        (None, "MA", None),
        (None, None, "US"),
        ("Boston", "MA", None),
    ],
    ids=[
        "missing_city",
        "missing_region_and_country",
        "missing_city_and_country",
        "missing_city_and_region",
        "missing_country",
    ],
)
def test_validate_suggest_custom_location_params(
    city, region, country, caplog: pytest.LogCaptureFixture, filter_caplog: FilterCaplogFixture
):
    """Test that validation method throws a Http 400 error with incomplete location params"""
    caplog.set_level(logging.INFO)

    with pytest.raises(HTTPException) as exc_info:
        validate_suggest_custom_location_params(city, region, None, None, country)
    assert exc_info.value.status_code == 400
    assert (
        exc_info.value.detail
        == "Invalid query parameters: either  all of `city`, `region`, `country` need to be present or "
        "all of `city`, `admin1`, and/or `admin2`, `country` need to be present."
    )

    records = filter_caplog(caplog.records, "merino.utils.api.query_params")

    assert len(records) == 1
    assert (
        records[0].message
        == "HTTP 400: Invalid query parameters: either  all of `city`, `region`, `country` need to be present or "
        "all of `city`, `admin1`, and/or `admin2`, `country` need to be present."
    )


def test_refine_geolocation_for_suggestion_with_all_params(geolocation: Location):
    """Test that refine geolocation method returns correct geolocation with updated params when all params are provided"""
    mock_request = Mock(spec=Request)

    expected_location: Location = Location(
        country="US",
        country_name="United States",
        regions=["NY"],
        region_names=["Washington"],
        city="New York",
        dma=819,
        postal_code="98354",
    )

    mock_request.scope = {ScopeKey.GEOLOCATION: geolocation}

    assert (
        refine_geolocation_for_suggestion(mock_request, "New York", ["NY"], "US")
        == expected_location
    )


def test_refine_geolocation_for_suggestion_with_incomplete_params(geolocation: Location):
    """Test that refine geolocation method returns original geolocation when incomplete params are provided"""
    mock_request = Mock(spec=Request)

    mock_request.scope = {ScopeKey.GEOLOCATION: geolocation}

    assert refine_geolocation_for_suggestion(mock_request, "New York", None, "US") == geolocation
