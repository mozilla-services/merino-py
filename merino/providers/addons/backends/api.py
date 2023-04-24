"""Dynamic Addons API"""
import requests

from merino.exceptions import BackendError
from merino.providers.addons.addons_data import STATIC_DATA
from merino.providers.addons.backends.protocol import Addon


class AddonAPIBackendException(BackendError):
    """Addon API Exception"""

    pass


class AddonAPIBackend:
    """Dynamic Addon Backend. This grabs the addon information
    from the Addon API endpoint, which means that we can
    be _current_ on the addon's rating and icon.
    """

    api_url: str

    def __init__(self, api_url: str):
        """Initialize Backend"""
        self.api_url = api_url

    async def get_addon(self, addon_key: str) -> Addon:
        """Get Addons given the list of keys"""
        static_info = STATIC_DATA[addon_key]
        return self._get_dynamic_addon_data(static_info, addon_key)

    def _get_dynamic_addon_data(
        self, static_data: dict[str, str], addon_key: str
    ) -> Addon:
        """Get the Addon information via the Addons API."""
        res = requests.get(f"{self.api_url}/{addon_key}")
        if res.status_code != 200:
            raise AddonAPIBackendException(
                f"Addons API could not find key: {addon_key}"
            )
        json_res = res.json()
        icon = json_res["icon_url"]
        rating = str(json_res["ratings"]["average"])

        return Addon(
            name=static_data["name"],
            description=static_data["description"],
            url=static_data["url"],
            icon=icon,
            rating=rating,
        )
