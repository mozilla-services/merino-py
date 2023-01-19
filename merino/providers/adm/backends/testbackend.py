"""Test backend for the AdM provider."""

from merino.providers.adm.backends.protocol import Content


class TestBackend:
    """A test backend that always returns empty results for tests."""

    async def fetch(self) -> Content:
        """Get fake Content from partner."""
        return Content()
