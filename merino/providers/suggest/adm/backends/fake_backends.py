"""Test backend for the AdM provider."""

from merino.providers.suggest.adm.backends.protocol import SuggestionContentExt
from moz_merino_ext.amp import AmpIndexManager


class FakeAdmBackend:  # pragma: no cover
    """A fake backend that always returns empty results."""

    async def fetch(self) -> SuggestionContentExt:
        """Get fake Content from partner."""
        return SuggestionContentExt(index_manager=AmpIndexManager(), icons={})  # type: ignore[no-untyped-call]
