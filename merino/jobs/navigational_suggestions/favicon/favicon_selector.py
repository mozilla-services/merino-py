"""Favicon selection logic for choosing the best favicon from multiple candidates"""

import logging
from typing import Any

from merino.jobs.navigational_suggestions.constants import FAVICON_SOURCE_PRIORITY

logger = logging.getLogger(__name__)


class FaviconSelector:
    """Select best favicon using Firefox's prioritization (source type, then size)."""

    @staticmethod
    def is_better_favicon(
        favicon: dict[str, Any], width: int, best_width: int, best_source: str
    ) -> bool:
        """Check if this favicon is better than current best."""
        source = favicon.get("_source", "default")

        current_priority = FAVICON_SOURCE_PRIORITY.get(source, 4)
        best_priority = FAVICON_SOURCE_PRIORITY.get(best_source, 4)

        # Lower priority number = higher priority (link=1 is better than meta=2)
        if current_priority < best_priority:
            return True

        # If same source priority, prefer larger dimensions
        if current_priority == best_priority and width > best_width:
            return True

        return False

    @staticmethod
    def select_best_favicon(
        favicons: list[dict[str, Any]],
        dimensions: list[tuple[int, int]],
        min_width: int = 0,
    ) -> tuple[dict[str, Any] | None, int]:
        """Select best favicon from candidates meeting minimum width requirement."""
        if not favicons or len(favicons) != len(dimensions):
            return None, 0

        best_favicon = None
        best_width = 0
        best_source = "default"

        for favicon, (width, height) in zip(favicons, dimensions):
            # Use minimum of width and height to handle non-square images
            favicon_width = min(width, height)

            if FaviconSelector.is_better_favicon(favicon, favicon_width, best_width, best_source):
                best_favicon = favicon
                best_width = favicon_width
                best_source = favicon.get("_source", "default")

        # Check if best favicon meets minimum width requirement
        if best_favicon and best_width >= min_width:
            return best_favicon, best_width

        return None, 0
