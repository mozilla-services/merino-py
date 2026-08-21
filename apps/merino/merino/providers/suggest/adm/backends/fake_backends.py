"""Test backend for the AdM provider."""

from merino.providers.suggest.adm.backends.protocol import SuggestionContent
from moz_merino_ext.amp import AmpIndexManager


class FakeAdmBackend:  # pragma: no cover
    """A fake backend that always returns empty results."""

    async def fetch(self) -> SuggestionContent:
        """Get fake Content from partner."""
        return SuggestionContent(index_manager=AmpIndexManager(), icons={})  # type: ignore[no-untyped-call]
