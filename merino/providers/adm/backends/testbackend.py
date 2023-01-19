"""Test backend for the AdM provider."""

from merino.providers.adm.backends.protocol import SuggestionContent


class TestBackend:
    """A test backend that always returns empty results for tests."""

    async def fetch(self) -> SuggestionContent:
        """Get fake Content from partner."""
        return SuggestionContent()
