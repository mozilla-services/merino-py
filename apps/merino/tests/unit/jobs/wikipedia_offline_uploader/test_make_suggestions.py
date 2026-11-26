"""Tests make suggestions."""

from unittest.mock import Mock

import freezegun
import pytest

from merino.jobs.wikipedia_offline_uploader import get_wiki_suggestions
from merino.jobs.wikipedia_offline_uploader.top_n_by_frequency import (
    INTERNAL_PAGES,
    load_language_blocklist,
)
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

    suggestions = list(scan(language, data, 0.25))
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
            "score": 0.25,
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

    results = make_suggestions(language, 3, data, 0.25)
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
    await get_wiki_suggestions("en", "all-access", 2, 0.25)

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
    await get_wiki_suggestions("en,fr", "all-access", 3, 0.25)

    assert mock_fetch.call_count == 6


@pytest.mark.asyncio
async def test_get_wiki_suggestions_passes_the_blocklist_dir_to_frequency(mocker, tmp_path):
    """Test the blocklist directory reaches the frequency ranking of each language."""
    mocker.patch("merino.jobs.wikipedia_offline_uploader.downloader.fetch_url")
    mock_top_n = mocker.patch(
        "merino.jobs.wikipedia_offline_uploader.downloader.get_top_n_frequency",
        return_value=[],
    )

    await get_wiki_suggestions("en,fr", "all-access", 1, 0.25, tmp_path)

    assert [c.args[0] for c in mock_top_n.call_args_list] == ["en", "fr"]
    assert all(c.args[3] == tmp_path for c in mock_top_n.call_args_list)


@pytest.mark.parametrize(
    ["title", "expected"],
    [
        ("Special:Search", True),
        ("Catégorie:Économie", True),
        ("Star_Wars,_épisode_III_:_La_Revanche_des_Sith", False),
        ("April_Fools'_Day", False),
    ],
    ids=["ascii_namespace", "accented_namespace", "spaced_colon_in_title", "regular_article"],
)
def test_internal_pages(title, expected):
    """Test INTERNAL_PAGES matches namespaced pages but not regular articles."""
    assert bool(INTERNAL_PAGES.search(title)) is expected


@pytest.mark.parametrize(
    ["rows", "expected"],
    [
        (None, set()),
        ([], set()),
        (
            ["aGVyY3VsZV9wb2lyb3Q=", "cGFyaXMsX2ZyYW5jZQ=="],
            {"hercule_poirot", "paris,_france"},
        ),
    ],
    ids=["no_file", "header_only", "decodes_titles"],
)
def test_load_language_blocklist(tmp_path, rows, expected):
    """Test the titles of `{language}-latest.csv` are base64 decoded."""
    if rows is not None:
        (tmp_path / "en-latest.csv").write_text("\n".join(["title", *rows]))

    assert load_language_blocklist(tmp_path, "en") == expected
