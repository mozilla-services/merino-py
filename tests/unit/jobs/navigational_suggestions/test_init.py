# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for navigational_suggestions __init__.py module."""

from merino.jobs.navigational_suggestions import _construct_top_picks


def test_construct_top_picks_source_field():
    """Test that _construct_top_picks includes the source field in the output JSON data."""
    # Mock input data
    domain_data = [
        {"rank": 1, "categories": ["web"], "source": "top-picks"},
        {"rank": 2, "categories": ["shopping"], "source": "custom-domains"},
    ]

    favicons = ["icon1", "icon2"]

    domain_metadata = [
        {"domain": "example.com", "url": "https://example.com", "title": "Example"},
        {"domain": "amazon.ca", "url": "https://amazon.ca", "title": "Amazon"},
    ]

    result = _construct_top_picks(domain_data, favicons, domain_metadata)

    # Check if source field is included correctly in the results
    assert "domains" in result
    assert len(result["domains"]) == 2
    assert result["domains"][0]["source"] == "top-picks"
    assert result["domains"][1]["source"] == "custom-domains"

    # Check other fields
    assert result["domains"][0]["domain"] == "example.com"
    assert result["domains"][0]["url"] == "https://example.com"
    assert result["domains"][0]["title"] == "Example"
    assert result["domains"][0]["icon"] == "icon1"

    assert result["domains"][1]["domain"] == "amazon.ca"
    assert result["domains"][1]["url"] == "https://amazon.ca"
    assert result["domains"][1]["title"] == "Amazon"
    assert result["domains"][1]["icon"] == "icon2"
