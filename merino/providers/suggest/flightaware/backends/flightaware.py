"""A wrapper for Flight Aware API interactions."""

from httpx import AsyncClient

from merino.providers.suggest.flightaware.backends.protocol import FlightBackendProtocol


class FlightAwareBackend(FlightBackendProtocol):
    """Backend that connects to the Flight Aware API."""

    api_key: str
    http_client: AsyncClient

    def __init__(
        self,
        api_key: str,
    ) -> None:
        """Initialize the flight aware backend."""
        self.api_key = api_key

    async def shutdown(self) -> None:
        """Shutdown any persistent connections. Currently a no-op."""
        pass
