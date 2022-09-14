"""The middleware that parses geolocation from the client IP address."""
import logging
from typing import Optional

import geoip2.database
from geoip2.errors import AddressNotFoundError
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from merino.config import settings

reader = geoip2.database.Reader(settings.location.maxmind_database)

logger = logging.getLogger(__name__)


class Location(BaseModel):
    """Data model for geolocation."""

    country: Optional[str] = None
    region: Optional[str] = None
    city: Optional[str] = None
    dma: Optional[int] = None


class GeolocationMiddleware(BaseHTTPMiddleware):
    """A middleware to populate geolocation from client's IP address.

    The geolocation result `Location` (if any) is stored in
    `Request.state.location`.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Provide Geolocation before handling request"""
        # `request.client.host` should be the first remote client address of `X-Forwarded-For`.
        record = None
        try:
            record = reader.city(request.client.host or "" if request.client else "")
        except ValueError:
            logger.warning("Invalid IP address for geolocation parsing")
        except AddressNotFoundError:
            pass

        request.state.location = (
            Location(
                country=record.country.iso_code,
                region=record.subdivisions[0].iso_code,
                city=record.city.names["en"],
                dma=record.location.metro_code,
            )
            if record
            else Location()
        )

        return await call_next(request)
