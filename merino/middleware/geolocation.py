import logging
from typing import Optional

import maxminddb
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from merino.config import settings

reader = maxminddb.open_database(settings.location.maxmind_database)

logger = logging.getLogger(__name__)


class Location(BaseModel):
    """
    Data model for geolocation.
    """

    country: Optional[str] = None
    region: Optional[str] = None
    city: Optional[str] = None
    dma: Optional[int] = None


class GeolocationMiddleware(BaseHTTPMiddleware):
    """
    A middleware to populate geolocation from client's IP address.

    The geolocation result `Location` (if any) is stored in `Request.state.location`.
    """

    async def dispatch(self, request: Request, call_next):
        # `request.client.host` should be the first remote client address of `X-Forwarded-For`.
        record = None
        try:
            record = reader.get(request.client.host)
        except ValueError:
            logger.warning("Invalid IP address for geolocation parsing")

        request.state.location = (
            Location(
                country=record["country"].get("iso_code"),
                region=record["subdivisions"][0].get("iso_code"),
                city=record["city"]["names"].get("en"),
                dma=record["location"].get("metro_code"),
            )
            if record
            else Location()
        )

        return await call_next(request)
