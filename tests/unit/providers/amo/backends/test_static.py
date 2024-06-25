"""Test StaticAddonsBackend."""

from typing import Any

import pytest

from merino.providers.amo.addons_data import ADDON_DATA, SupportedAddon
from merino.providers.amo.backends.protocol import Addon
from merino.providers.amo.backends.static import (
    STATIC_RATING_AND_ICONS,
    StaticAmoBackend,
)


@pytest.fixture(name="static_backend")
def fixture_static_backend() -> StaticAmoBackend:
    """Create a RemoteSettingsBackend object for test."""
    return StaticAmoBackend()


@pytest.mark.asyncio
async def test_get_addon_success(static_backend: StaticAmoBackend):
    """Test that we can get Addon information statically."""
    addons = await static_backend.get_addon(SupportedAddon.VIDEO_DOWNLOADER)
    video_downloader: dict[str, str] = ADDON_DATA[SupportedAddon.VIDEO_DOWNLOADER]
    vd_icon_rating: dict[str, Any] = STATIC_RATING_AND_ICONS[SupportedAddon.VIDEO_DOWNLOADER]
    assert (
        Addon(
            name=video_downloader["name"],
            description=video_downloader["description"],
            url=video_downloader["url"],
            icon=vd_icon_rating["icon"],
            rating=vd_icon_rating["rating"],
            number_of_ratings=vd_icon_rating["number_of_ratings"],
            guid=video_downloader["guid"],
        )
        == addons
    )
