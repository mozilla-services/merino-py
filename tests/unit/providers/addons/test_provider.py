"""Test Addon Provider"""
import pytest

from merino.middleware.geolocation import Location
from merino.providers.addons.addons_data import STATIC_DATA
from merino.providers.addons.backends.static import (
    STATIC_RATING_AND_ICONS,
    StaticAddonsBackend,
)
from merino.providers.addons.provider import Provider as AddonsProvider
from merino.providers.addons.provider import TemporaryAddonSuggestion
from merino.providers.base import SuggestionRequest
from merino.providers.custom_details import AddonsDetails, CustomDetails


@pytest.fixture(name="keywords")
def fixture_keywords() -> dict[str, set[str]]:
    """Fixture for the keywords."""
    return {
        "video-downloadhelper": {"addon", "download helper"},
        "languagetool": {
            "dictionary",
        },
    }


@pytest.fixture(name="static_backend")
def fixture_static_backend() -> StaticAddonsBackend:
    """Fixture for static backend."""
    return StaticAddonsBackend()


@pytest.fixture(name="addons_provider")
def fixture_addon_provider(
    keywords: dict[str, set[str]], static_backend: StaticAddonsBackend
) -> AddonsProvider:
    """Fixture for Addon Provider."""
    return AddonsProvider(
        backend=static_backend,
        keywords=keywords,
        name="addons",
        score=0.3,
        min_chars=4,
    )


def test_reverse_and_expand_keywords(
    static_backend: StaticAddonsBackend, keywords: dict[str, set[str]]
):
    """Test that we expand the keywords properly for the lookup table."""
    provider = AddonsProvider(
        backend=static_backend, keywords=keywords, name="addons", score=0.3, min_chars=4
    )

    assert {
        "addo": "video-downloadhelper",
        "addon": "video-downloadhelper",
        "down": "video-downloadhelper",
        "downl": "video-downloadhelper",
        "downlo": "video-downloadhelper",
        "downloa": "video-downloadhelper",
        "download": "video-downloadhelper",
        "download ": "video-downloadhelper",
        "download h": "video-downloadhelper",
        "download he": "video-downloadhelper",
        "download hel": "video-downloadhelper",
        "download help": "video-downloadhelper",
        "download helpe": "video-downloadhelper",
        "download helper": "video-downloadhelper",
        "dict": "languagetool",
        "dicti": "languagetool",
        "dictio": "languagetool",
        "diction": "languagetool",
        "dictiona": "languagetool",
        "dictionar": "languagetool",
        "dictionary": "languagetool",
    } == provider.addon_keywords


@pytest.mark.asyncio
async def test_query_string_too_short(
    addons_provider: AddonsProvider,
):
    """Test that we return no suggestion for a query that is too short."""
    req = SuggestionRequest(query="a", geolocation=Location())
    assert [] == await addons_provider.query(req)


@pytest.mark.asyncio
async def test_query_no_keyword_matches(
    addons_provider: AddonsProvider,
):
    """Test that a keyword that doesn't match any current keywords returns no results."""
    req = SuggestionRequest(query="amazing", geolocation=Location())
    assert [] == await addons_provider.query(req)


@pytest.mark.asyncio
async def test_query_return_match(
    addons_provider: AddonsProvider,
):
    """Test that we match one provider."""
    req = SuggestionRequest(query="dictionary", geolocation=Location())
    expected_info = STATIC_DATA["languagetool"]
    expected_icon_rating = STATIC_RATING_AND_ICONS["languagetool"]
    assert [
        TemporaryAddonSuggestion(
            title=expected_info["name"],
            description=expected_info["description"],
            url=expected_info["url"],
            score=0.3,
            is_sponsored=True,
            provider="addons",
            icon=expected_icon_rating["icon"],
            custom_details=CustomDetails(
                addons=AddonsDetails(rating=expected_icon_rating["rating"])
            ),
        )
    ] == await addons_provider.query(req)
