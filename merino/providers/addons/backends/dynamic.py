"""Dynamic Addons API"""
import requests
from httpx import AsyncClient

from merino.exceptions import BackendError
from merino.providers.addons.addons_data import ADDON_DATA, SUPPORTED_ADDONS_KEYS
from merino.providers.addons.backends.protocol import Addon


class DynamicAddonsBackendException(BackendError):
    """Dynamic Addon Exception"""

    pass


class DynamicAddonsBackend:
    """Dynamic Addon Backend. This grabs the addon information
    from the Addon API endpoint, which means that we can
    be _current_ on the addon's rating and icon.

    However, we will still use the STATIC_DATA of the Addons as those are the
    description and name of the Addons provided by product.
    They are not meant to be updated as frequently as reviews or icons.
    If this changes in the future, we can update the code to also get
    the information dynamically from the Addons API.
    """

    api_url: str

    def __init__(self, api_url: str):
        """Initialize Backend"""
        self.api_url = api_url
        self.dynamic_data = {}

    async def initialize_addons(self) -> Addon:
        """Initialize the dynamic Addon information via the Addons API."""
        self.dynamic_data = {}  # ensure that it's empty
        for addon_key in SUPPORTED_ADDONS_KEYS:
            async with AsyncClient() as client:
                res = await client.get(
                    f"{self.api_url}/{addon_key}", follow_redirects=True
                )

            if res.status_code != 200:
                raise DynamicAddonsBackendException(
                    f"Addons API could not find key: {addon_key}"
                )

            json_res = res.json()
            icon = json_res["icon_url"]
            rating = str(json_res["ratings"]["average"])

            self.dynamic_data[addon_key] = {"icon": icon, "rating": rating}

    async def get_addon(self, addon_key: str) -> Addon:
        """Get an Addon based on the addon_key"""
        static_info: dict[str, str] = ADDON_DATA[addon_key]
        icon_and_rating: dict[str, str] = self.dynamic_data[addon_key]
        return Addon(
            name=static_info["name"],
            description=static_info["description"],
            url=static_info["url"],
            icon=icon_and_rating["icon"],
            rating=icon_and_rating["rating"],
        )
