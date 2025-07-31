"""Tests make suggestions."""

from unittest.mock import Mock

import freezegun
import pytest

from merino.jobs.wikipedia_offline_uploader import get_wiki_suggestions
from merino.jobs.wikipedia_offline_uploader.make_suggestions import (
    make_keywords,
    scan,
    make_suggestions,
)


def test_make_keywords():
    """Test make keywords return list of partials."""
    words = ["the", "suggestion"]
    result = make_keywords(words)

    assert result == [
        "the su",
        "the sug",
        "the sugg",
        "the sugge",
        "the sugges",
        "the suggest",
        "the suggesti",
        "the suggestio",
        "the suggestion",
    ]


def test_make_keywords_with_seen_words(mocker):
    """Test make keywords return list of partials that aren't in SEEN_KEYWORDS."""
    seen_words = ["the su", "the sun"]
    words = ["the", "suggestion"]

    mocker.patch(
        "merino.jobs.wikipedia_offline_uploader.make_suggestions.SEEN_KEYWORDS",
        new=set(seen_words),
    )
    result = make_keywords(words)

    assert result == [
        "the sug",
        "the sugg",
        "the sugge",
        "the sugges",
        "the suggest",
        "the suggesti",
        "the suggestio",
        "the suggestion",
    ]


def test_scan(mocker):
    """Test scan returns proper suggestion data."""
    mocker.patch(
        "merino.jobs.wikipedia_offline_uploader.make_suggestions.make_keywords",
        return_value={"te", "tes", "test", "test w", "test wi", "test wik", "test wiki"},
    )
    language = "en"
    data = [{"title": "test wiki"}]

    suggestions = list(scan(language, data))
    assert suggestions == [
        {
            "advertiser": "Wikipedia",
            "full_keywords": [["test wiki", 7]],
            "iab_category": "5 - Education",
            "icon": "161351842074695",
            "id": 0,
            "keywords": {"te", "tes", "test", "test w", "test wi", "test wik", "test wiki"},
            "title": "Wikipedia - test wiki",
            "url": "https://en.wikipedia.org/wiki/test%20wiki",
        },
    ]


def test_make_suggestions_return_correct_num_of_suggestions(mocker):
    """Test make_suggestions returns correct number of suggestions."""
    mock_scan_return_value = (
        {
            "id": i,
            "keywords": [f"kw{i}"],
            "title": f"title{i}",
            "url": "",
            "iab_category": "",
            "icon": "",
            "advertiser": "",
            "full_keywords": [["title", 1]],
        }
        for i in range(10)
    )
    mocker.patch(
        "merino.jobs.wikipedia_offline_uploader.make_suggestions.scan",
        return_value=mock_scan_return_value,
    )
    language = "en"
    data = [{"title": f"Title_{i}"} for i in range(10)]

    results = make_suggestions(language, 3, data)
    assert len(results) == 3


@pytest.mark.asyncio
@freezegun.freeze_time("2025-06-19 03:21:34")
async def test_get_wiki_suggestions(mocker):
    """Test get_wiki_suggestions retrieves the right amount of data."""
    mock_fetch_wiki_get_return_value = {
        "items": [
            {
                "project": "en.wikipedia",
                "access": "desktop",
                "year": "2025",
                "month": "06",
                "day": "18",
                "articles": [
                    {"article": "Main_Page", "views": 2312218, "rank": 1},
                    {"article": "Special:Search", "views": 704745, "rank": 2},
                    {"article": "April_Fools'_Day", "views": 130082, "rank": 3},
                ],
            }
        ]
    }
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = mock_fetch_wiki_get_return_value
    mock_response.raise_for_status = Mock()
    mock_fetch = mocker.patch(
        "merino.jobs.wikipedia_offline_uploader.downloader.requests.get",
        return_value=mock_response,
    )
    await get_wiki_suggestions("en", "frequency", "all-access", 2)

    assert mock_fetch.call_count == 2


@pytest.mark.asyncio
@freezegun.freeze_time("2025-06-19 03:21:34")
async def test_get_wiki_suggestions_multi_lang(mocker):
    """Test get_wiki_suggestions retrieves the right amount of data."""
    mock_fetch_wiki_get_return_value = {
        "items": [
            {
                "project": "en.wikipedia",
                "access": "desktop",
                "year": "2025",
                "month": "06",
                "day": "18",
                "articles": [
                    {"article": "Main_Page", "views": 2312218, "rank": 1},
                    {"article": "Special:Search", "views": 704745, "rank": 2},
                    {"article": "April_Fools'_Day", "views": 130082, "rank": 3},
                ],
            }
        ]
    }
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = mock_fetch_wiki_get_return_value
    mock_response.raise_for_status = Mock()
    mock_fetch = mocker.patch(
        "merino.jobs.wikipedia_offline_uploader.downloader.requests.get",
        return_value=mock_response,
    )
    await get_wiki_suggestions("en,fr", "recency", "all-access", 3)

    assert mock_fetch.call_count == 6
