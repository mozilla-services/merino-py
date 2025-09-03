"""SportsData live query system"""

from typing import Any


class SportSuggestion(dict):
    """Return a well structured Suggestion for the UA to process"""

    # Required fields.
    provider: str
    rating: float

    def as_suggestion(self) -> dict[str, Any]:
        return dict(
            provider=self.provider,
            rating=self.rating,
            # Return the random values we've collected as the "custom details"
            custom_details=dict(zip(self.keys(), self.values())),
        )
