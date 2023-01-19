"""Test backend for the AdM provider."""

from merino.providers.adm.backends.protocol import SuggestionContent


class FakeAdmBackend:
    """A fake backend that always returns empty results."""

    async def fetch(self) -> SuggestionContent:
        """Get fake Content from partner."""
        return SuggestionContent()
