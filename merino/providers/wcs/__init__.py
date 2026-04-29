"""Module dedicated to providing World Cup Soccer match data to New Tab."""

from merino.providers.wcs.provider import WcsProvider

_provider = WcsProvider()


def get_provider() -> WcsProvider:
    """Return the singleton WCS provider for FastAPI's `Depends`."""
    return _provider
