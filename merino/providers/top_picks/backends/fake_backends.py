"""Test backend for the Top Picks provider."""

from merino.providers.top_picks.backends.protocol import TopPicksData


class FakeTopPicksBackend:  # pragma: no cover
    """A fake test backend that always returns empty results."""

    async def fetch(self) -> TopPicksData:
        """Get fake Top Picks data."""
        return TopPicksData()  # type: ignore [call-arg]
