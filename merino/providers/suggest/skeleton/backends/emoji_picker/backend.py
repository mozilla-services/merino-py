"""Silly example emoji picker"""

from merino.providers.suggest.skeleton.backends.protocol import (
    SkeletonBackend,
    SkeletonData,
)
from merino.providers.suggest.base import BaseSuggestion
from merino.providers.suggest.skeleton.backends.emoji_picker import EmojiPickerError
from merino.providers.suggest.skeleton.backends.emoji_picker.protocol import EmojiData


class EmojiPickerBackend(SkeletonBackend):
    """Provide the methods specific to this provider for fulfilling the request"""

    async def query(self, description: str | None = None) -> list[BaseSuggestion]:
        """Eventually use clever logic in order to return an emoji specific to the
        passed description string, but for now, just return the default in a list.
        """

        return [EmojiData().as_suggestion()]
