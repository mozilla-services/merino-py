"""The middleware that parses geolocation from the client IP address."""

import logging
import unicodedata
from typing import Optional

import geoip2.database
from geoip2.errors import AddressNotFoundError
from pydantic import BaseModel
from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from merino.config import settings
from merino.middleware import ScopeKey

CLIENT_IP_OVERRIDE: str = settings.location.client_ip_override

reader = geoip2.database.Reader(settings.location.maxmind_database)

logger = logging.getLogger(__name__)


class Coordinates(BaseModel):
    """Data model for coordinates for geolocation."""

    latitude: Optional[float] = None
    longitude: Optional[float] = None
    radius: Optional[int] = None


class Location(BaseModel):
    """Data model for geolocation."""

    country: Optional[str] = None
    country_name: Optional[str] = None
    regions: Optional[list[str]] = None
    region_names: Optional[list[str]] = None
    city: Optional[str] = None
    dma: Optional[int] = None
    postal_code: Optional[str] = None
    key: Optional[str] = None
    coordinates: Optional[Coordinates] = None


def normalize_string(input_str) -> str:
    """Normalize string with special characters."""
    return unicodedata.normalize("NFKD", input_str).encode("ascii", "ignore").decode("ascii")


def get_regions(subdivisions) -> Optional[list[str]]:
    """Get all the iso_codes from subdivisions."""
    return [s.iso_code for s in reversed(subdivisions)] or None


def get_region_names(subdivisions) -> Optional[list[str]]:
    """Get all the region names from subdivisions."""
    return [s.names.get("en") for s in reversed(subdivisions)] or None


class GeolocationMiddleware:
    """An ASGI middleware to parse and populate geolocation from client's IP
    address.

    The geolocation result `Location` (if any) is stored in
    `scope[ScopeKey.GEOLOCATION]`.
    """

    def __init__(self, app: ASGIApp) -> None:
        """Initialize."""
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Parse geolocation through client's IP address and store the result
        to `scope`.
        """
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope=scope)
        record = None
        ip_address = CLIENT_IP_OVERRIDE or (request.client.host or "" if request.client else "")
        try:
            record = reader.city(ip_address)
        except ValueError:
            logger.warning("Invalid IP address for geolocation parsing")
        except AddressNotFoundError:
            pass

        scope[ScopeKey.GEOLOCATION] = (
            Location(
                country=record.country.iso_code,
                country_name=record.country.names.get("en"),
                regions=get_regions(record.subdivisions),
                region_names=get_region_names(record.subdivisions),
                city=normalize_string(city) if (city := record.city.names.get("en")) else None,
                dma=record.location.metro_code,
                postal_code=record.postal.code if record.postal else None,
                coordinates=Coordinates(
                    latitude=record.location.latitude,
                    longitude=record.location.longitude,
                    radius=record.location.accuracy_radius,
                ),
            )
            if record
            else Location()
        )

        await self.app(scope, receive, send)
        return
