"""Dynamic AMO Backend"""
import logging
from asyncio import Task, TaskGroup
from json import JSONDecodeError
from typing import Any

import httpx
from httpx import AsyncClient

from merino.providers.amo.addons_data import ADDON_DATA, SupportedAddon
from merino.providers.amo.backends.protocol import Addon, AmoBackendError
from merino.utils.http_client import create_http_client

AMO_CONNECT_TIMEOUT: float = 10.0

logger = logging.getLogger(__name__)


class DynamicAmoBackendException(AmoBackendError):
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

    async def _fetch_addon(
        self, client: AsyncClient, addon_key: SupportedAddon
    ) -> dict[str, Any] | None:
        """Fetch addon metadata via AMO. Return `None` on errors."""
        try:
            res = await client.get(f"{self.api_url}/{addon_key}", follow_redirects=True)
        except httpx.HTTPError as e:
            logger.error(
                f"Addons API failed request to fetch addon: {addon_key}, {e}, {e.__class__}"
            )
            return None

        try:
            res.raise_for_status()

            json_res = res.json()
            return {
                "icon": json_res["icon_url"],
                "rating": f"{(json_res['ratings']['average']):.1f}",
                "number_of_ratings": json_res["ratings"]["count"],
            }
        except httpx.HTTPError as e:
            logger.error(
                f"Addons API could not find key: {addon_key}, {e}, {e.__class__}"
            )
        except (KeyError, JSONDecodeError):
            logger.error(
                "Problem with Addons API formatting. "
                "Check that the API response structure hasn't changed."
            )

        return None

    async def fetch_and_cache_addons_info(self) -> None:
        """Get the dynamic AMO information via the Addons API.
        Allow for partial initialization if the response object is not available
        at the moment. We do not want to block initialization or take down the
        provider for some missing information.
        """
        tasks: list[Task] = []

        try:
            async with (
                create_http_client(connect_timeout=AMO_CONNECT_TIMEOUT) as client,
                TaskGroup() as group,
            ):
                for addon_key in SupportedAddon:
                    tasks.append(
                        group.create_task(
                            self._fetch_addon(client, addon_key), name=addon_key
                        )
                    )

            # Update in place without clearing out the map so that fetch failures
            # will not overwrite the old values.
            self.dynamic_data |= [
                (SupportedAddon(task.get_name()), await task)
                for task in tasks
                if await task is not None
            ]
        except ExceptionGroup as e:
            raise AmoBackendError(e.exceptions)

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
            number_of_ratings=int(icon_and_rating["number_of_ratings"]),
            guid=static_info["guid"],
        )
