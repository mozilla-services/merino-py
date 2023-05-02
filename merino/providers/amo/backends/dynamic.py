"""Dynamic AMO Backend"""
import logging
from json import JSONDecodeError

import httpx
from httpx import AsyncClient

from merino.exceptions import BackendError
from merino.providers.amo.addons_data import ADDON_DATA, SupportedAddon
from merino.providers.amo.backends.protocol import Addon


class DynamicAmoBackendException(BackendError):
    """Dynamic Amo Exception"""

    pass


class DynamicAmoBackend:
    """Dynamic AMO Backend. This grabs the addon information
    from the Addon API endpoint, which means that we can
    be _current_ on the addon's rating and icon.

    However, we will still use the STATIC_DATA of the Addons as those are the
    description and name of the Addons provided by product.
    They are not meant to be updated as frequently as reviews or icons.
    If this changes in the future, we can update the code to also get
    the information dynamically from the Addons API.
    """

    api_url: str
    dynamic_data: dict[SupportedAddon, dict[str, str]]

    def __init__(self, api_url: str):
        """Initialize Backend"""
        self.api_url = api_url
        self.dynamic_data = {}

    async def initialize_addons(self) -> None:
        """Initialize the dynamic AMO information via the Addons API.
        Allow for partial initialization if the response object is not available
        at the moment. We do not want to block initialization or take down the
        provider for some missing information.
        """
        self.dynamic_data = {}  # ensure that it's empty
        for addon_key in SupportedAddon:
            async with AsyncClient() as client:
                try:
                    res = await client.get(
                        f"{self.api_url}/{addon_key}", follow_redirects=True
                    )
                    res.raise_for_status()

                    json_res = res.json()
                    icon = json_res["icon_url"]
                    rating = str(json_res["ratings"]["average"])

                except httpx.HTTPError:
                    logging.error(f"Addons API could not find key: {addon_key}")

                except (KeyError, JSONDecodeError):
                    logging.error(
                        "Problem with Addons API formatting. "
                        "Check that the API response structure hasn't changed."
                    )

            self.dynamic_data[addon_key] = {"icon": icon, "rating": rating}

    async def get_addon(self, addon_key: SupportedAddon) -> Addon:
        """Get an Addon based on the addon_key"""
        static_info: dict[str, str] = ADDON_DATA[addon_key]
        try:
            icon_and_rating: dict[str, str] = self.dynamic_data[addon_key]
        except KeyError:
            raise DynamicAmoBackendException(
                "Missing Addon in execution. Skip returning Addon."
            )

        return Addon(
            name=static_info["name"],
            description=static_info["description"],
            url=static_info["url"],
            icon=icon_and_rating["icon"],
            rating=icon_and_rating["rating"],
        )
