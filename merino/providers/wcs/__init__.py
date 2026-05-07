"""Module dedicated to providing World Cup Soccer match data to New Tab."""

from merino.providers.wcs.provider import WcsProvider
from merino.configs import settings

_provider = WcsProvider(settings=settings.providers.sports)


def get_provider() -> WcsProvider:
    """Return the singleton WCS provider for FastAPI's `Depends`."""
    return _provider
