"""Test backends"""
from typing import Any
from urllib.parse import quote


class TestBackend:  # pragma: no cover
    """A mock backend for testing."""

    async def shutdown(self) -> None:
        """Nothing to shut down."""
        return None

    async def search(self, _: str) -> list[dict[str, Any]]:
        """Return an empty list."""
        return []


class TestEchoBackend:
    """A mock backend for testing.

    It returns the exact same query as the search result.
    """

    async def shutdown(self) -> None:
        """Nothing to shut down."""
        return None

    async def search(self, q: str) -> list[dict[str, Any]]:
        """Echoing the query as the single suggestion."""
        return [
            {
                "full_keyword": q,
                "title": q,
                "url": f"""https://en.wikipedia.org/wiki/{quote(q.replace(" ", "_"))}""",
            }
        ]
