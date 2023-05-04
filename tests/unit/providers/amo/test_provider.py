"""Test Addon Provider"""
import pytest
from _pytest.logging import LogCaptureFixture

from merino.middleware.geolocation import Location
from merino.providers.amo.addons_data import ADDON_DATA, SupportedAddon
from merino.providers.amo.backends.protocol import Addon, AmoBackendError
from merino.providers.amo.backends.static import (
    STATIC_RATING_AND_ICONS,
    StaticAmoBackend,
)
from merino.providers.amo.provider import AddonSuggestion
from merino.providers.amo.provider import Provider as AddonsProvider
from merino.providers.amo.provider import invert_and_expand_index_keywords
from merino.providers.base import SuggestionRequest
from merino.providers.custom_details import AmoDetails, CustomDetails


class AmoErrorBackend:
    """AmoBackend that raises an error for testing."""

    async def get_addon(self, addon_key: SupportedAddon) -> Addon:  # pragma: no cover
        """Get an Addon based on the addon_key.
        Raise a `BackendError` if the addon key is missing.
        """
        raise AmoBackendError("Error!!!")

    async def initialize_addons(self) -> None:
        """Initialize addons to be stored."""
        pass


@pytest.fixture(name="keywords")
def fixture_keywords() -> dict[SupportedAddon, set[str]]:
    """Fixture for the keywords."""
    return {
        SupportedAddon.VIDEO_DOWNLOADER: {"addon", "download helper"},
        SupportedAddon.LANGAUGE_TOOL: {
            "dictionary",
        },
    }


@pytest.fixture(name="static_backend")
def fixture_static_backend() -> StaticAmoBackend:
    """Fixture for static backend."""
    return StaticAmoBackend()


@pytest.fixture(name="addons_provider")
def fixture_addon_provider(
    keywords: dict[SupportedAddon, set[str]], static_backend: StaticAmoBackend
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


def test_reverse_and_expand_keywords(keywords: dict[SupportedAddon, set[str]]):
    """Test that we expand the keywords properly for the lookup table."""
    assert {
        "addo": SupportedAddon.VIDEO_DOWNLOADER,
        "addon": SupportedAddon.VIDEO_DOWNLOADER,
        "down": SupportedAddon.VIDEO_DOWNLOADER,
        "downl": SupportedAddon.VIDEO_DOWNLOADER,
        "downlo": SupportedAddon.VIDEO_DOWNLOADER,
        "downloa": SupportedAddon.VIDEO_DOWNLOADER,
        "download": SupportedAddon.VIDEO_DOWNLOADER,
        "download ": SupportedAddon.VIDEO_DOWNLOADER,
        "download h": SupportedAddon.VIDEO_DOWNLOADER,
        "download he": SupportedAddon.VIDEO_DOWNLOADER,
        "download hel": SupportedAddon.VIDEO_DOWNLOADER,
        "download help": SupportedAddon.VIDEO_DOWNLOADER,
        "download helpe": SupportedAddon.VIDEO_DOWNLOADER,
        "download helper": SupportedAddon.VIDEO_DOWNLOADER,
        "dict": SupportedAddon.LANGAUGE_TOOL,
        "dicti": SupportedAddon.LANGAUGE_TOOL,
        "dictio": SupportedAddon.LANGAUGE_TOOL,
        "diction": SupportedAddon.LANGAUGE_TOOL,
        "dictiona": SupportedAddon.LANGAUGE_TOOL,
        "dictionar": SupportedAddon.LANGAUGE_TOOL,
        "dictionary": SupportedAddon.LANGAUGE_TOOL,
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
    expected_info = ADDON_DATA[SupportedAddon.LANGAUGE_TOOL]
    expected_icon_rating = STATIC_RATING_AND_ICONS[SupportedAddon.LANGAUGE_TOOL]
    assert [
        AddonSuggestion(
            title=expected_info["name"],
            description=expected_info["description"],
            url=expected_info["url"],
            score=0.3,
            provider="addons",
            icon=expected_icon_rating["icon"],
            custom_details=CustomDetails(
                addons=AmoDetails(
                    rating=expected_icon_rating["rating"],
                    number_of_ratings=expected_icon_rating["number_of_ratings"],
                )
            ),
        )
    ] == await addons_provider.query(req)


@pytest.mark.asyncio
async def test_query_error(
    caplog: LogCaptureFixture, keywords: dict[SupportedAddon, set[str]]
):
    """Test that provider can handle query error."""
    provider = AddonsProvider(
        backend=AmoErrorBackend(),
        keywords=keywords,
        name="addons",
        score=0.3,
        min_chars=4,
    )
    await provider.initialize()

    req = SuggestionRequest(query="dictionary", geolocation=Location())
    suggestions = await provider.query(req)
    assert suggestions == []

    assert len(caplog.messages) == 1
    assert caplog.messages[0].startswith("Error getting AMO suggestion:")
