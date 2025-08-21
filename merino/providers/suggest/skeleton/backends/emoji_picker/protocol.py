"""Protocol definitions for the example "Emoji Picker"

This should include various data type and derivatives that your example class requires.

"""

from merino.providers.suggest.base import BaseSuggestion
from merino.providers.suggest.skeleton import SkeletonData


class EmojiData(SkeletonData):
    """The contained result we want to return to the Web API"""

    emoji: str
    description: str

    def __init__(self, emoji: str | None = None, description: str | None = None):
        self.emoji = "🤷"
        self.description = "A person shrugging"

    def as_suggestion(self) -> BaseSuggestion:
        """Normalize whatever data we might be using into a standard Suggestion"""
        return BaseSuggestion(
            title=self.emoji,
            description=self.description,
            url=self.url,
            provider=self.provider,
            is_sponsored=False,
            score=self.score,
        )
