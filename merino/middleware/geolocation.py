"""The middleware that parses geolocation from the client IP address."""
import logging
from contextvars import ContextVar
from typing import Optional

import geoip2.database
from geoip2.errors import AddressNotFoundError
from pydantic import BaseModel
from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from merino.config import settings

CLIENT_IP_OVERRIDE: str = settings.location.client_ip_override

reader = geoip2.database.Reader(settings.location.maxmind_database)

logger = logging.getLogger(__name__)


class Location(BaseModel):
    """Data model for geolocation."""

    country: Optional[str] = None
    region: Optional[str] = None
    city: Optional[str] = None
    dma: Optional[int] = None
    postal_code: Optional[str] = None


# A `ContextVar` to store the geolocation result.
ctxvar_geolocation: ContextVar[Location] = ContextVar("merino_geolocation")


class GeolocationMiddleware:
    """An ASGI middleware to parse and populate geolocation from client's IP
    address.

    The geolocation result `Location` (if any) is stored in a `ContextVar` called
    `merino_geolocation`.
    """

    def __init__(self, app: ASGIApp) -> None:
        """Initialize."""
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Parse geolocation through client's IP address and store the result
        (if any) to the `ContextVar`.
        """
        if scope["type"] != "http":  # pragma: no cover
            await self.app(scope, receive, send)
            return

        request = Request(scope=scope)
        record = None
        ip_address = CLIENT_IP_OVERRIDE or (
            request.client.host or "" if request.client else ""
        )
        try:
            record = reader.city(ip_address)
        except ValueError:
            logger.warning("Invalid IP address for geolocation parsing")
        except AddressNotFoundError:
            pass

        ctxvar_geolocation.set(
            Location(
                country=record.country.iso_code,
                region=record.subdivisions[0].iso_code,
                city=record.city.names["en"],
                dma=record.location.metro_code,
                postal_code=record.postal.code if record.postal else None,
            )
            if record
            else Location()
        )

        await self.app(scope, receive, send)
        return
