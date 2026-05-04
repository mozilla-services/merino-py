"""Protocol for WCS provider backends."""

from typing import Protocol

from merino.providers.wcs.protocol import EventInfo


class WcsBackend(Protocol):
    """Protocol for a backend that supplies WCS match events.

    `get_events()` provides the full schedule for the matches endpoint.
    `get_live_events()` provides events for the live endpoint; implementations
    may return a live feed, a static subset, or fake in-progress data.
    """

    def get_events(self) -> list[EventInfo]:  # pragma: no cover
        """Return the full list of available match events."""
        ...

    def get_live_events(self) -> list[EventInfo]:  # pragma: no cover
        """Return events that may currently be in progress."""
        ...
