"""Fixtures for manifest files"""

import pytest


@pytest.fixture(scope="module")
def mock_manifest_2024() -> dict:
    """Mock manifest json for the year 2024"""
    return {
        "domains": [
            {
                "rank": 1,
                "domain": "google",
                "categories": ["Search Engines"],
                "serp_categories": [0],
                "url": "https://www.google.com",
                "title": "Google",
                "icon": "chrome://activity-stream/content/data/content/tippytop/images/google-com@2x.png",
            }
        ]
    }


@pytest.fixture(scope="module")
def mock_manifest_2025() -> dict:
    """Mock manifest json for the year 2025"""
    return {
        "domains": [
            {
                "rank": 1,
                "domain": "spotify",
                "categories": ["Entertainment"],
                "serp_categories": [0],
                "url": "https://www.spotify.com",
                "title": "Spotify",
                "icon": "chrome://activity-stream/content/data/content/tippytop/images/google-com@2x.png",
            }
        ]
    }
