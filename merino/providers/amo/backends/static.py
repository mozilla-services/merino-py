"""Static Addon Endpoint"""
from typing import Any

from merino.providers.amo.addons_data import ADDON_DATA, SupportedAddon
from merino.providers.amo.backends.protocol import Addon

STATIC_RATING_AND_ICONS = {
    SupportedAddon.VIDEO_DOWNLOADER: {
        "rating": "4.284",
        "number_of_ratings": 23477,
        "icon": "https://addons.mozilla.org/user-media/addon_icons/3/3006-64.png",
    },
    SupportedAddon.LANGAUGE_TOOL: {
        "rating": "4.7452",
        "number_of_ratings": 3430,
        "icon": "https://addons.mozilla.org/user-media/addon_icons/708/708770-64.png",
    },
    SupportedAddon.PRIVATE_RELAY: {
        "rating": "4.117",
        "number_of_ratings": 1349,
        "icon": "https://addons.mozilla.org/user-media/addon_icons/2633/2633704-64.png",
    },
    SupportedAddon.SEARCH_BY_IMAGE: {
        "rating": "4.6515",
        "number_of_ratings": 1255,
        "icon": "https://addons.mozilla.org/user-media/addon_icons/824/824288-64.png",
    },
    SupportedAddon.DARKREADER: {
        "rating": "4.5586",
        "number_of_ratings": 4962,
        "icon": "https://addons.mozilla.org/user-media/addon_icons/855/855413-64.png",
    },
    SupportedAddon.PRIVACY_BADGER: {
        "rating": "4.8009",
        "number_of_ratings": 2223,
        "icon": "https://addons.mozilla.org/user-media/addon_icons/506/506646-64.png",
    },
    SupportedAddon.UBLOCK_ORIGIN: {
        "rating": "4.781",
        "number_of_ratings": 15329,
        "icon": "https://addons.mozilla.org/user-media/addon_icons/607/607454-64.png",
    },
    SupportedAddon.READ_ALOUD: {
        "rating": "3.9603",
        "number_of_ratings": 757,
        "icon": "https://addons.mozilla.org/user-media/addon_icons/952/952959-64.png",
    },
}


class StaticAmoBackend:
    """Static Amo Backend. This backend is mainly useful for
    tests and potentially a fallback if the API is broken.
    """

    async def fetch_and_cache_addons_info(self) -> None:
        """Get extra addons information. Pass for static Addons."""
        pass

    async def get_addon(self, addon_key: SupportedAddon) -> Addon:
        """Get an Addon based on the addon_key"""
        static_info: dict[str, str] = ADDON_DATA[addon_key]
        icon_and_rating: dict[str, Any] = STATIC_RATING_AND_ICONS[addon_key]

        return Addon(
            name=static_info["name"],
            description=static_info["description"],
            url=static_info["url"],
            icon=icon_and_rating["icon"],
            rating=icon_and_rating["rating"],
            number_of_ratings=icon_and_rating["number_of_ratings"],
            guid=static_info["guid"],
        )
