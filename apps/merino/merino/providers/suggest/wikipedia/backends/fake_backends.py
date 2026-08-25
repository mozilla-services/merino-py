"""Test backends"""

from typing import Any
from urllib.parse import quote

from merino.exceptions import BackendError


class FakeWikipediaBackend:  # pragma: no cover
    """A fake backend that always returns empty results."""

    async def shutdown(self) -> None:
        """Nothing to shut down."""
        return None

    async def search(self, _: str, language_code: str) -> list[dict[str, Any]]:
        """Return an empty list."""
        return []


class FakeEchoWikipediaBackend:
    """A fake backend that returns the exact same query as the search result."""

    async def shutdown(self) -> None:
        """Nothing to shut down."""
        return None

    async def search(self, q: str, language_code: str) -> list[dict[str, Any]]:
        """Echoing the query as the single suggestion."""
        return [
            {
                "full_keyword": q,
                "title": q,
                "url": f"""https://{language_code}.wikipedia.org/wiki/{quote(q.replace(" ", "_"))}""",
            }
        ]


class FakeExceptionWikipediaBackend:  # pragma: no cover
    """A fake backend that raises a `BackendError` for any given query."""

    async def shutdown(self) -> None:
        """Nothing to shut down."""
        return None

    async def search(self, q: str, language_code: str) -> list[dict[str, Any]]:
        """Echoing the query as the single suggestion."""
        raise BackendError("A backend failure")
