"""Test Addon Provider"""
import pytest

from merino.middleware.geolocation import Location
from merino.providers.addons.addons_data import ADDON_DATA, SupportedAddons
from merino.providers.addons.backends.static import (
    STATIC_RATING_AND_ICONS,
    StaticAddonsBackend,
)
from merino.providers.addons.provider import AddonSuggestion
from merino.providers.addons.provider import Provider as AddonsProvider
from merino.providers.addons.provider import invert_and_expand_index_keywords
from merino.providers.base import SuggestionRequest
from merino.providers.custom_details import AddonsDetails, CustomDetails


@pytest.fixture(name="keywords")
def fixture_keywords() -> dict[SupportedAddons, set[str]]:
    """Fixture for the keywords."""
    return {
        SupportedAddons.VIDEO_DOWNLOADER: {"addon", "download helper"},
        SupportedAddons.LANGAUGE_TOOL: {
            "dictionary",
        },
    }


@pytest.fixture(name="static_backend")
def fixture_static_backend() -> StaticAddonsBackend:
    """Fixture for static backend."""
    return StaticAddonsBackend()


@pytest.fixture(name="addons_provider")
def fixture_addon_provider(
    keywords: dict[SupportedAddons, set[str]], static_backend: StaticAddonsBackend
) -> AddonsProvider:
    """Fixture for Addon Provider."""
    provider = AddonsProvider(
        backend=static_backend,
        keywords=keywords,
        name="addons",
        score=0.3,
        min_chars=4,
    )
    return provider


def test_reverse_and_expand_keywords(keywords: dict[SupportedAddons, set[str]]):
    """Test that we expand the keywords properly for the lookup table."""
    assert {
        "addo": SupportedAddons.VIDEO_DOWNLOADER,
        "addon": SupportedAddons.VIDEO_DOWNLOADER,
        "down": SupportedAddons.VIDEO_DOWNLOADER,
        "downl": SupportedAddons.VIDEO_DOWNLOADER,
        "downlo": SupportedAddons.VIDEO_DOWNLOADER,
        "downloa": SupportedAddons.VIDEO_DOWNLOADER,
        "download": SupportedAddons.VIDEO_DOWNLOADER,
        "download ": SupportedAddons.VIDEO_DOWNLOADER,
        "download h": SupportedAddons.VIDEO_DOWNLOADER,
        "download he": SupportedAddons.VIDEO_DOWNLOADER,
        "download hel": SupportedAddons.VIDEO_DOWNLOADER,
        "download help": SupportedAddons.VIDEO_DOWNLOADER,
        "download helpe": SupportedAddons.VIDEO_DOWNLOADER,
        "download helper": SupportedAddons.VIDEO_DOWNLOADER,
        "dict": SupportedAddons.LANGAUGE_TOOL,
        "dicti": SupportedAddons.LANGAUGE_TOOL,
        "dictio": SupportedAddons.LANGAUGE_TOOL,
        "diction": SupportedAddons.LANGAUGE_TOOL,
        "dictiona": SupportedAddons.LANGAUGE_TOOL,
        "dictionar": SupportedAddons.LANGAUGE_TOOL,
        "dictionary": SupportedAddons.LANGAUGE_TOOL,
    } == invert_and_expand_index_keywords(keywords, 4)


@pytest.mark.asyncio
async def test_query_string_too_short(
    addons_provider: AddonsProvider,
):
    """Test that we return no suggestion for a query that is too short."""
    await addons_provider.initialize()
    req = SuggestionRequest(query="a", geolocation=Location())
    assert [] == await addons_provider.query(req)


@pytest.mark.asyncio
async def test_query_no_keyword_matches(
    addons_provider: AddonsProvider,
):
    """Test that a keyword that doesn't match any current keywords returns no results."""
    await addons_provider.initialize()
    req = SuggestionRequest(query="amazing", geolocation=Location())
    assert [] == await addons_provider.query(req)


@pytest.mark.asyncio
async def test_query_return_match(
    addons_provider: AddonsProvider,
):
    """Test that we match one provider."""
    await addons_provider.initialize()

    req = SuggestionRequest(query="dictionary", geolocation=Location())
    expected_info = ADDON_DATA[SupportedAddons.LANGAUGE_TOOL]
    expected_icon_rating = STATIC_RATING_AND_ICONS[SupportedAddons.LANGAUGE_TOOL]
    assert [
        AddonSuggestion(
            title=expected_info["name"],
            description=expected_info["description"],
            url=expected_info["url"],
            score=0.3,
            provider="addons",
            icon=expected_icon_rating["icon"],
            custom_details=CustomDetails(
                addons=AddonsDetails(rating=expected_icon_rating["rating"])
            ),
        )
    ] == await addons_provider.query(req)
