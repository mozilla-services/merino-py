"""Test backend for the AdM provider."""

from merino.providers.suggest.adm.backends.protocol import GlobalSuggestionContent


class FakeAdmBackend:  # pragma: no cover
    """A fake backend that always returns empty results."""

    async def fetch(self) -> GlobalSuggestionContent:
        """Get fake Content from partner."""
        return GlobalSuggestionContent()  # type: ignore [call-arg]
