"""Default WCS backend: static schedule for matches, fake data for live."""

from datetime import UTC, datetime

from merino.providers.wcs.fake_data import build_events as build_fake_events
from merino.providers.wcs.protocol import EventInfo
from merino.providers.wcs.schedules import build_events


class DefaultWcsBackend:
    """Serves the static schedule for matches and fake in-progress events for live."""

    def get_events(self) -> list[EventInfo]:
        """Return all match events from the bundled schedule file."""
        return build_events()

    def get_live_events(self) -> list[EventInfo]:
        """Return fake events anchored to today so the live bucket is always populated."""
        return build_fake_events(datetime.now(UTC).date())
